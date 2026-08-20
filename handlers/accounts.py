import asyncio
import contextlib
import io
import logging

import qrcode
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, BufferedInputFile
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter
from states.forms import AddAccountStates
from keyboards.inline import (
    accounts_menu_keyboard,
    account_add_method_keyboard,
    account_code_keyboard,
    back_keyboard,
    account_list_keyboard,
    account_detail_keyboard,
    confirm_delete_keyboard,
    account_qr_keyboard,
)
from database import db
from services import telethon_manager as tm
from utils.filters import AdminFilter

logger = logging.getLogger(__name__)
router = Router()
router.message.filter(AdminFilter())
router.callback_query.filter(AdminFilter())

_qr_wait_tasks: dict[int, asyncio.Task] = {}


def _build_qr_photo(url: str) -> BufferedInputFile:
    qr = qrcode.QRCode(box_size=10, border=2)
    qr.add_data(url)
    qr.make(fit=True)
    image = qr.make_image(fill_color="black", back_color="white")

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return BufferedInputFile(buffer.getvalue(), filename="telegram-login-qr.png")


def _normalize_phone(phone: str | None) -> str | None:
    if not phone:
        return None
    return phone if phone.startswith("+") else f"+{phone}"


async def _cancel_qr_task(owner_id: int):
    task = _qr_wait_tasks.pop(owner_id, None)
    if task:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


async def _cancel_qr_flow(owner_id: int):
    await _cancel_qr_task(owner_id)
    await tm.cancel_qr_auth(owner_id)


async def _cancel_phone_flow(state: FSMContext):
    data = await state.get_data()
    phone = data.get("phone")
    auth_mode = data.get("auth_mode")
    if auth_mode == "phone" and phone:
        await tm.disconnect_and_remove(phone)


async def _cancel_active_auth(state: FSMContext, owner_id: int):
    await _cancel_qr_flow(owner_id)
    await _cancel_phone_flow(state)


def _format_next_delivery_hint(next_type: str | None) -> str | None:
    hints = {
        "CodeTypeSms": "ℹ️ Agar hozircha kod kelmasa, keyingi urinish SMS orqali bo'lishi mumkin.",
        "CodeTypeCall": "ℹ️ Agar kod kelmasa, Telegram keyingi urinishda qo'ng'iroqdan foydalanishi mumkin.",
        "CodeTypeFlashCall": "ℹ️ Agar kod kelmasa, keyingi urinish flash call orqali bo'lishi mumkin.",
        "CodeTypeMissedCall": "ℹ️ Agar kod kelmasa, Telegram keyingi urinishda missed call ishlatishi mumkin.",
        "CodeTypeFragmentSms": "ℹ️ Agar kod kelmasa, keyingi urinish Fragment SMS orqali bo'lishi mumkin.",
    }
    return hints.get(next_type)


def _build_code_message(auth_info: dict[str, str | int | bool | None]) -> str:
    response_lines = [
        "🔄 Tasdiqlash kodi qayta yuborildi."
        if auth_info.get("is_resend")
        else "📨 Tasdiqlash kodi yuborildi."
    ]

    delivery_hint = auth_info.get("delivery_hint")
    if delivery_hint:
        response_lines.append(str(delivery_hint))

    next_delivery_hint = _format_next_delivery_hint(auth_info.get("next_type"))
    if next_delivery_hint:
        response_lines.append(next_delivery_hint)

    timeout_seconds = auth_info.get("timeout_seconds")
    if isinstance(timeout_seconds, int) and timeout_seconds > 0:
        response_lines.append(
            f"⏱️ Agar darrov ko'rinmasa, taxminan {timeout_seconds} soniya kuting."
        )

    code_length = auth_info.get("code_length")
    if isinstance(code_length, int) and code_length > 0:
        response_lines.append(f"🔢 {code_length} xonali tasdiqlash kodini kiriting:")
    else:
        response_lines.append("🔢 Telegramdan kelgan tasdiqlash kodini kiriting:")

    return "\n".join(response_lines)


async def _save_account(phone: str | None, session_string: str):
    normalized_phone = _normalize_phone(phone)
    if not normalized_phone:
        raise RuntimeError("Akkaunt telefon raqamini aniqlab bo'lmadi.")

    if await db.get_account_by_phone(normalized_phone):
        raise RuntimeError(f"{normalized_phone} akkaunti allaqachon qo'shilgan.")

    await db.add_account(normalized_phone, session_string)
    return normalized_phone


async def _watch_qr_login(bot, chat_id: int, owner_id: int, state: FSMContext):
    try:
        session_string, me, needs_2fa = await tm.wait_for_qr_auth(owner_id)
        if needs_2fa:
            await state.update_data(auth_mode="qr", qr_owner_id=owner_id)
            await state.set_state(AddAccountStates.waiting_2fa)
            await bot.send_message(chat_id, "🔐 QR login tasdiqlandi. Endi 2FA parolini kiriting:")
            return

        phone = await _save_account(getattr(me, "phone", None), session_string)
        await state.clear()
        await bot.send_message(
            chat_id,
            f"✅ Akkaunt qo'shildi!\n👤 <b>{me.first_name}</b> ({phone})",
            reply_markup=accounts_menu_keyboard(),
            parse_mode="HTML",
        )
    except asyncio.TimeoutError:
        await state.clear()
        await bot.send_message(
            chat_id,
            "⌛ QR kod muddati tugadi. Xohlasangiz yangisini yarating.",
            reply_markup=account_qr_keyboard(),
        )
    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.error(f"QR auth xatosi owner={owner_id}: {e}")
        await state.clear()
        await bot.send_message(
            chat_id,
            f"❌ QR login xatoligi: {e}",
            reply_markup=accounts_menu_keyboard(),
        )
    finally:
        _qr_wait_tasks.pop(owner_id, None)


async def _send_qr_login(message: Message, state: FSMContext, owner_id: int):
    await _cancel_qr_flow(owner_id)

    qr_info = await tm.begin_qr_auth(owner_id)
    await state.clear()
    await state.update_data(auth_mode="qr", qr_owner_id=owner_id)
    await state.set_state(AddAccountStates.waiting_qr_scan)

    expires_in = qr_info["expires_in"]
    caption = (
        "🔳 <b>QR login</b>\n\n"
        "1. Akkaunt kirilgan rasmiy Telegram ilovasini oching.\n"
        "2. <b>Settings -> Devices -> Link Desktop Device</b> bo'limiga kiring.\n"
        "3. Pastdagi QR kodni skan qiling.\n\n"
        f"⏳ QR taxminan {expires_in} soniya amal qiladi."
    )

    await message.answer_photo(
        _build_qr_photo(qr_info["url"]),
        caption=caption,
        reply_markup=account_qr_keyboard(),
        parse_mode="HTML",
    )
    _qr_wait_tasks[owner_id] = asyncio.create_task(
        _watch_qr_login(message.bot, message.chat.id, owner_id, state)
    )


@router.callback_query(F.data == "menu_accounts")
async def cb_accounts_menu(callback: CallbackQuery, state: FSMContext):
    await _cancel_active_auth(state, callback.from_user.id)
    await state.clear()
    await callback.message.edit_text(
        "👤 <b>Ulangan telegram akkauntlar:</b>",
        reply_markup=accounts_menu_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "account_add")
async def cb_account_add(callback: CallbackQuery, state: FSMContext):
    await _cancel_active_auth(state, callback.from_user.id)
    await state.clear()
    await callback.message.edit_text(
        "➕ <b>Akkaunt qo'shish</b>\n\nUsulni tanlang:",
        reply_markup=account_add_method_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "account_add_phone")
async def cb_account_add_phone(callback: CallbackQuery, state: FSMContext):
    await _cancel_active_auth(state, callback.from_user.id)
    await state.set_state(AddAccountStates.waiting_phone)
    await callback.message.edit_text(
        "📱 Telefon raqamini kiriting:\n<i>Misol: +998901234567</i>",
        reply_markup=back_keyboard("account_add"),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "account_add_qr")
async def cb_account_add_qr(callback: CallbackQuery, state: FSMContext):
    await callback.answer("QR tayyorlanmoqda...")
    try:
        await _cancel_phone_flow(state)
        await _send_qr_login(callback.message, state, callback.from_user.id)
    except Exception as e:
        logger.error(f"QR boshlash xatosi owner={callback.from_user.id}: {e}")
        await state.clear()
        await callback.message.answer(
            f"❌ QR login boshlanmadi: {e}",
            reply_markup=accounts_menu_keyboard(),
        )


@router.callback_query(F.data == "account_qr_refresh")
async def cb_account_qr_refresh(callback: CallbackQuery, state: FSMContext):
    await callback.answer("Yangi QR yaratilmoqda...")
    try:
        await _send_qr_login(callback.message, state, callback.from_user.id)
    except Exception as e:
        logger.error(f"QR refresh xatosi owner={callback.from_user.id}: {e}")
        await state.clear()
        await callback.message.answer(
            f"❌ Yangi QR yaratilmadi: {e}",
            reply_markup=accounts_menu_keyboard(),
        )


@router.callback_query(F.data == "account_qr_cancel")
async def cb_account_qr_cancel(callback: CallbackQuery, state: FSMContext):
    await _cancel_qr_flow(callback.from_user.id)
    await state.clear()
    await callback.message.answer(
        "❌ QR login bekor qilindi.",
        reply_markup=accounts_menu_keyboard(),
    )
    await callback.answer()


@router.message(StateFilter(AddAccountStates.waiting_phone))
async def msg_phone(message: Message, state: FSMContext):
    phone = (message.text or "").strip()
    if not phone.startswith("+") or not phone[1:].isdigit():
        await message.answer("❌ Noto'g'ri format. Misol: +998901234567")
        return
    await message.answer("⏳ Kod yuborilmoqda...")
    try:
        auth_info = await tm.begin_auth(phone)
        await state.update_data(phone=phone, auth_mode="phone")
        await state.set_state(AddAccountStates.waiting_code)
        await message.answer(
            _build_code_message(auth_info),
            reply_markup=account_code_keyboard(),
        )
    except Exception as e:
        logger.error(f"begin_auth xatosi {phone}: {e}")
        await state.clear()
        await message.answer(
            f"❌ Xatolik: {e}\n\nQayta urinib ko'ring.",
            reply_markup=accounts_menu_keyboard(),
        )


@router.callback_query(F.data == "account_code_resend")
async def cb_account_code_resend(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    phone = data.get("phone")
    auth_mode = data.get("auth_mode")
    if auth_mode != "phone" or not phone:
        await state.clear()
        await callback.message.answer(
            "❌ Sessiya tugadi. Qayta boshlang.",
            reply_markup=accounts_menu_keyboard(),
        )
        await callback.answer()
        return

    await callback.answer("Kod qayta yuborilmoqda...")
    try:
        auth_info = await tm.begin_auth(phone)
        await callback.message.answer(
            _build_code_message(auth_info),
            reply_markup=account_code_keyboard(),
        )
    except Exception as e:
        logger.error(f"begin_auth resend xatosi {phone}: {e}")
        await callback.message.answer(
            f"❌ Xatolik: {e}\n\nBirozdan keyin qayta urinib ko'ring.",
            reply_markup=account_code_keyboard(),
        )


@router.callback_query(F.data == "account_code_cancel")
async def cb_account_code_cancel(callback: CallbackQuery, state: FSMContext):
    await _cancel_phone_flow(state)
    await state.clear()
    await callback.message.answer(
        "❌ Telefon orqali login bekor qilindi.",
        reply_markup=accounts_menu_keyboard(),
    )
    await callback.answer()


@router.message(StateFilter(AddAccountStates.waiting_qr_scan))
async def msg_qr_waiting(message: Message):
    await message.answer(
        "🔳 Hozir QR login kutilmoqda. QR kodni skan qiling yoki pastdagi tugmalar orqali yangilang/bekor qiling."
    )


@router.message(StateFilter(AddAccountStates.waiting_code))
async def msg_code(message: Message, state: FSMContext):
    code = message.text.strip().replace(" ", "")
    data = await state.get_data()
    phone = data.get("phone")
    if not phone:
        await state.clear()
        await message.answer(
            "❌ Sessiya tugadi. Qayta boshlang.", reply_markup=accounts_menu_keyboard()
        )
        return
    try:
        session_string, me, needs_2fa = await tm.complete_auth(phone, code)
        if needs_2fa:
            await state.set_state(AddAccountStates.waiting_2fa)
            await message.answer("🔐 2FA parolini kiriting:")
        else:
            saved_phone = await _save_account(phone, session_string)
            await state.clear()
            await message.answer(
                f"✅ Akkaunt qo'shildi!\n👤 <b>{me.first_name}</b> ({saved_phone})",
                reply_markup=accounts_menu_keyboard(),
                parse_mode="HTML",
            )
    except Exception as e:
        logger.error(f"complete_auth xatosi {phone}: {e}")
        await message.answer(
            f"❌ Xatolik: {e}\n\nKod noto'g'ri bo'lishi mumkin.",
            reply_markup=account_code_keyboard(),
        )


@router.message(StateFilter(AddAccountStates.waiting_2fa))
async def msg_2fa(message: Message, state: FSMContext):
    password = message.text.strip()
    data = await state.get_data()
    auth_mode = data.get("auth_mode")

    if auth_mode == "qr":
        owner_id = data.get("qr_owner_id")
        if not owner_id:
            await state.clear()
            await message.answer(
                "❌ Sessiya tugadi. Qayta boshlang.", reply_markup=accounts_menu_keyboard()
            )
            return
        try:
            session_string, me = await tm.complete_qr_auth_2fa(owner_id, password)
            saved_phone = await _save_account(getattr(me, "phone", None), session_string)
            await state.clear()
            await message.answer(
                f"✅ Akkaunt qo'shildi!\n👤 <b>{me.first_name}</b> ({saved_phone})",
                reply_markup=accounts_menu_keyboard(),
                parse_mode="HTML",
            )
        except Exception as e:
            logger.error(f"complete_qr_auth_2fa xatosi owner={owner_id}: {e}")
            await message.answer(f"❌ Xatolik: {e}\n\nParol noto'g'ri bo'lishi mumkin.")
        return

    phone = data.get("phone")
    if not phone:
        await state.clear()
        await message.answer(
            "❌ Sessiya tugadi. Qayta boshlang.", reply_markup=accounts_menu_keyboard()
        )
        return
    try:
        session_string, me = await tm.complete_auth_2fa(phone, password)
        saved_phone = await _save_account(phone, session_string)
        await state.clear()
        await message.answer(
            f"✅ Akkaunt qo'shildi!\n👤 <b>{me.first_name}</b> ({saved_phone})",
            reply_markup=accounts_menu_keyboard(),
            parse_mode="HTML",
        )
    except Exception as e:
        logger.error(f"complete_auth_2fa xatosi {phone}: {e}")
        await message.answer(f"❌ Xatolik: {e}\n\nParol noto'g'ri bo'lishi mumkin.")


@router.callback_query(F.data == "account_list")
async def cb_account_list(callback: CallbackQuery):
    accounts = await db.get_all_accounts()
    if not accounts:
        await callback.message.edit_text(
            "📋 Hozircha akkauntlar yo'q.",
            reply_markup=back_keyboard("menu_accounts"),
        )
    else:
        await callback.message.edit_text(
            f"📋 <b>Akkauntlar ro'yxati</b> ({len(accounts)} ta):",
            reply_markup=account_list_keyboard(accounts),
            parse_mode="HTML",
        )
    await callback.answer()


@router.callback_query(F.data.startswith("account_view_"))
async def cb_account_view(callback: CallbackQuery):
    account_id = int(callback.data.removeprefix("account_view_"))
    acc = await db.get_account_by_id(account_id)
    if not acc:
        await callback.answer("Akkaunt topilmadi.", show_alert=True)
        return
    status_text = "✅ Faol" if acc["is_active"] else "❌ Nofaol"
    text = (
        f"👤 <b>Akkaunt ma'lumotlari</b>\n\n"
        f"📱 Telefon: <code>{acc['phone']}</code>\n"
        f"📊 Holat: {status_text}\n"
        f"📅 Qo'shilgan: {acc['created_at']}"
    )
    await callback.message.edit_text(
        text,
        reply_markup=account_detail_keyboard(account_id),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("account_delete_confirm_"))
async def cb_account_delete_confirm(callback: CallbackQuery):
    account_id = int(callback.data.removeprefix("account_delete_confirm_"))
    acc = await db.get_account_by_id(account_id)
    if not acc:
        await callback.answer("Akkaunt topilmadi.", show_alert=True)
        return
    await tm.disconnect_and_remove(acc["phone"])
    await db.delete_account(account_id)
    await callback.message.edit_text(
        "✅ Akkaunt muvaffaqiyatli o'chirildi.",
        reply_markup=back_keyboard("account_list"),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("account_delete_"))
async def cb_account_delete_ask(callback: CallbackQuery):
    account_id = int(callback.data.removeprefix("account_delete_"))
    acc = await db.get_account_by_id(account_id)
    if not acc:
        await callback.answer("Akkaunt topilmadi.", show_alert=True)
        return
    await callback.message.edit_text(
        f"⚠️ <b>{acc['phone']}</b> akkauntini o'chirishni tasdiqlaysizmi?",
        reply_markup=confirm_delete_keyboard(account_id),
        parse_mode="HTML",
    )
    await callback.answer()
