import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter

from database import db
from keyboards.inline import (
    groups_menu_keyboard,
    group_list_keyboard,
    group_detail_keyboard,
    back_keyboard,
)
from services import telethon_manager as tm
from states.forms import GroupAddStates
from utils.filters import AdminFilter

logger = logging.getLogger(__name__)
router = Router()
router.message.filter(AdminFilter())
router.callback_query.filter(AdminFilter())


@router.callback_query(F.data == "menu_groups")
async def cb_menu_groups(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    groups = await db.get_all_groups()
    await callback.message.edit_text(
        f"🏘 <b>Guruhlar boshqaruvi</b>\n\n"
        f"Bazasidagi jami guruhlar soni: <b>{len(groups)} ta</b>\n\n"
        f"Bo'limni tanlang:",
        reply_markup=groups_menu_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "group_add_username")
async def cb_group_add_username(callback: CallbackQuery, state: FSMContext):
    await state.set_state(GroupAddStates.waiting_username)
    await callback.message.edit_text(
        "✍️ <b>Guruh username yoki havolasini kiriting:</b>\n\n"
        "Misol: <code>@toshkent_taksi</code> yoki <code>https://t.me/toshkent_taksi</code>",
        reply_markup=back_keyboard("menu_groups"),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(StateFilter(GroupAddStates.waiting_username))
async def msg_group_add_username(message: Message, state: FSMContext):
    username_input = message.text.strip()
    accounts = await db.get_active_accounts()
    if not accounts:
        await message.answer(
            "❌ Tizimda faol akkaunt topilmadi. Avval **👤 Akkauntlar -> ➕ Akkaunt qo'shish** bo'limidan akkaunt qo'shing."
        )
        return

    status_msg = await message.answer(
        f"⏳ <code>{username_input}</code> kiritilmoqda va guruh ma'lumotlari yuklanmoqda...",
        parse_mode="HTML",
    )

    group_info = None
    last_error = None
    invalid_phones = []

    for acc in accounts:
        try:
            group_info = await tm.add_group_by_username(
                acc["session_string"], acc["phone"], username_input
            )
            if group_info:
                break
        except Exception as e:
            err_str = str(e)
            logger.error(f"Group add error ({username_input}) on {acc['phone']}: {err_str}")
            last_error = err_str
            if (
                "authorization has been invalidated" in err_str.lower()
                or "deauthorized" in err_str.lower()
                or "session" in err_str.lower()
            ):
                invalid_phones.append(acc["phone"])
                await tm.disconnect_and_remove(acc["phone"])
                await db.delete_account(acc["id"])

    if not group_info:
        err_text = f"❌ Guruh qo'shishda xatolik: {last_error}"
        if invalid_phones:
            err_text += f"\n\n⚠️ Sessiyasi bekor qilingan (chiqib ketilgan) akkaunt(lar) bazadan tozalandi: {', '.join(invalid_phones)}. Iltimos, **Akkauntlar** bo'limidan yangi akkaunt qo'shing."
        else:
            err_text += "\n\nUsername yoki havola to'g'riligini va akkaunt guruhga kirish huquqiga ega ekanini tekshiring."

        await status_msg.edit_text(
            err_text,
            reply_markup=back_keyboard("menu_groups"),
        )
        return

    await db.save_groups([group_info])
    await state.clear()
    try:
        await status_msg.delete()
    except Exception:
        pass

    groups = await db.get_all_groups()
    await message.answer(
        f"✅ <b>{group_info['title']}</b> guruhi muvaffaqiyatli qo'shildi!\n\n"
        f"🏘 <b>Guruhlar boshqaruvi</b>\n"
        f"Baza guruhlari soni: <b>{len(groups)} ta</b>",
        reply_markup=groups_menu_keyboard(),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "group_list")
async def cb_group_list(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    groups = await db.get_all_groups()
    if not groups:
        await callback.message.edit_text(
            "❌ Hali hech qanday guruh qo'shilmagan.",
            reply_markup=groups_menu_keyboard(),
        )
        await callback.answer()
        return

    await callback.message.edit_text(
        f"📋 <b>Guruhlar ro'yxati</b> ({len(groups)} ta):\n\n"
        f"Tafsilotlarni ko'rish va o'chirish uchun guruhni tanlang:",
        reply_markup=group_list_keyboard(groups),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("group_view_"))
async def cb_group_view(callback: CallbackQuery, state: FSMContext):
    group_db_id = int(callback.data.removeprefix("group_view_"))
    group = await db.get_group_by_id(group_db_id)
    if not group:
        await callback.answer("Guruh topilmadi", show_alert=True)
        return

    un = f"@{group['username']}" if group.get("username") else "Yo'q"
    await callback.message.edit_text(
        f"🏘 <b>Guruh tafsilotlari</b>\n\n"
        f"📌 <b>Nomi:</b> {group['title']}\n"
        f"🔗 <b>Username:</b> {un}\n"
        f"🆔 <b>Telegram ID:</b> <code>{group['group_id']}</code>",
        reply_markup=group_detail_keyboard(group_db_id),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("group_delete_"))
async def cb_group_delete(callback: CallbackQuery, state: FSMContext):
    group_db_id = int(callback.data.removeprefix("group_delete_"))
    await db.delete_group(group_db_id)
    await callback.answer("Guruh o'chirildi!", show_alert=True)

    groups = await db.get_all_groups()
    if not groups:
        await callback.message.edit_text(
            "📋 Hali hech qanday guruh qo'shilmagan.",
            reply_markup=groups_menu_keyboard(),
        )
    else:
        await callback.message.edit_text(
            f"📋 <b>Guruhlar ro'yxati</b> ({len(groups)} ta):",
            reply_markup=group_list_keyboard(groups),
            parse_mode="HTML",
        )


@router.callback_query(F.data == "group_clear_all")
async def cb_group_clear_all(callback: CallbackQuery, state: FSMContext):
    await db.delete_all_groups()
    await callback.answer("Barcha guruhlar tozalandi!", show_alert=True)
    groups = await db.get_all_groups()
    await callback.message.edit_text(
        f"🏘 <b>Guruhlar boshqaruvi</b>\n\n"
        f"Bazasidagi jami guruhlar soni: <b>{len(groups)} ta</b>\n\n"
        f"Bo'limni tanlang:",
        reply_markup=groups_menu_keyboard(),
        parse_mode="HTML",
    )
