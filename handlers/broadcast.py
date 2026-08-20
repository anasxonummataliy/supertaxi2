import json
import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter
from states.forms import BroadcastStates
from keyboards.inline import (
    broadcast_menu_keyboard,
    back_keyboard,
    accounts_checkbox_keyboard,
    groups_checkbox_keyboard,
    interval_keyboard,
    stagger_keyboard,
    broadcast_control_keyboard,
    broadcast_confirm_delete_keyboard,
    broadcast_stats_keyboard,
    broadcast_list_keyboard,
)
from database import db
from services import telethon_manager as tm
from services.broadcaster import BroadcastManager
from utils.filters import AdminFilter

logger = logging.getLogger(__name__)
router = Router()
router.message.filter(AdminFilter())
router.callback_query.filter(AdminFilter())

GROUPS_PAGE_SIZE = 10


def _clamp_groups_page(page: int, groups_count: int) -> int:
    max_page = max(0, (groups_count - 1) // GROUPS_PAGE_SIZE)
    return min(max(page, 0), max_page)


async def _render_groups_selection(
    callback: CallbackQuery,
    state: FSMContext,
    *,
    edit_text: bool = False,
):
    data = await state.get_data()
    groups = data.get("groups_list", [])
    selected = set(data.get("selected_groups", []))
    page = _clamp_groups_page(int(data.get("groups_page", 0)), len(groups))
    await state.update_data(groups_page=page)

    if not groups:
        text = (
            "🏘 <b>Hali guruhlar mavjud emas.</b>\n\n"
            "Pastdagi <b>➕ Guruh qo'shish (username)</b> tugmasi orqali guruh username/havolasini yuborib guruh qo'shing:"
        )
    else:
        text = f"🏘 Guruhlarni tanlang ({len(groups)} ta):"

    reply_markup = groups_checkbox_keyboard(
        groups,
        selected,
        page=page,
        page_size=GROUPS_PAGE_SIZE,
    )

    if edit_text:
        await callback.message.edit_text(text, reply_markup=reply_markup, parse_mode="HTML")
    else:
        await callback.message.edit_reply_markup(reply_markup=reply_markup)


def _build_broadcast_task_text(task_id: int, task: dict) -> str:
    account_ids = json.loads(task["account_ids"])
    group_ids = json.loads(task["group_ids"])
    status_map = {
        "running": "🟢 Ishlayapti",
        "paused": "🟡 Kutmoqda",
        "stopped": "🔴 To'xtatilgan",
    }
    short_msg = task["message_text"][:80] + (
        "..." if len(task["message_text"]) > 80 else ""
    )
    stagger = task.get("stagger_seconds", 60)
    return (
        f"📢 <b>Tarqatish #{task_id}</b>\n\n"
        f"📝 Xabar: <i>{short_msg}</i>\n"
        f"👥 Akkauntlar: {len(account_ids)} ta\n"
        f"🏘 Guruhlar: {len(group_ids)} ta\n"
        f"⏱ Interval: {task['interval_minutes']} daqiqa\n"
        f"⏳ Stagger: {stagger} sek\n"
        f"📊 Holat: {status_map.get(task['status'], task['status'])}\n"
        f"📅 Yaratilgan: {task['created_at']}"
    )


def _fmt_dt(dt) -> str:
    if dt is None:
        return "—"
    return dt.strftime("%H:%M:%S")


def _fmt_remaining(seconds) -> str:
    if seconds is None:
        return "—"
    seconds = int(seconds)
    if seconds <= 0:
        return "hozir"
    m, s = divmod(seconds, 60)
    if m == 0:
        return f"{s}s"
    return f"{m}d {s}s"


def _build_stats_text(task_id: int, task: dict, stats: list[dict]) -> str:
    status_map = {
        "running": "🟢 Ishlayapti",
        "paused": "🟡 Kutmoqda",
        "stopped": "🔴 To'xtatilgan",
    }
    lines = [
        f"📊 <b>Tarqatish #{task_id} — Statistika</b>",
        f"📌 Holat: {status_map.get(task['status'], task['status'])}",
        f"⏱ Interval: {task['interval_minutes']} daqiqa",
        "",
    ]
    for i, s in enumerate(stats, 1):
        active_mark = "✅" if s["is_active"] else "❌"
        lines.append(f"<b>{i}. {active_mark} {s['phone']}</b>")
        lines.append(f"   📤 Oxirgi yuborildi: {_fmt_dt(s['last_sent'])}")
        lines.append(f"   ⏭ Keyingi yuborish: {_fmt_dt(s['next_send'])}")
        lines.append(f"   ⏳ Qoldi: {_fmt_remaining(s['remaining_sec'])}")
        lines.append("")
    return "\n".join(lines).rstrip()


async def _render_broadcast_task(callback: CallbackQuery, task_id: int, task: dict):
    await callback.message.edit_text(
        _build_broadcast_task_text(task_id, task),
        reply_markup=broadcast_control_keyboard(task_id, task["status"]),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "menu_broadcast")
async def cb_broadcast_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        "📢 <b>Xabar tarqatish</b>",
        reply_markup=broadcast_menu_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "bcast_new")
async def cb_bcast_new(callback: CallbackQuery, state: FSMContext):
    await state.set_state(BroadcastStates.waiting_message)
    await callback.message.edit_text(
        "✏️ Tarqatmoqchi bo'lgan xabar matnini yozing:",
        reply_markup=back_keyboard("menu_broadcast"),
    )
    await callback.answer()


@router.message(StateFilter(BroadcastStates.waiting_message))
async def msg_broadcast_text(message: Message, state: FSMContext):
    if not message.text:
        await message.answer("❌ Faqat matnli xabar kiriting.")
        return
    accounts = await db.get_active_accounts()
    if not accounts:
        await state.clear()
        await message.answer(
            "❌ Faol akkauntlar yo'q. Avval akkaunt qo'shing.",
            reply_markup=broadcast_menu_keyboard(),
        )
        return
    await state.update_data(
        message_text=message.text,
        accounts_list=accounts,
        selected_accounts=[],
        selected_groups=[],
    )
    await state.set_state(BroadcastStates.selecting_accounts)
    await message.answer(
        "👥 Xabar yuboradigan akkauntlarni tanlang:",
        reply_markup=accounts_checkbox_keyboard(accounts, set()),
    )


@router.callback_query(
    F.data.startswith("bcast_acc_toggle_"),
    StateFilter(BroadcastStates.selecting_accounts),
)
async def cb_toggle_account(callback: CallbackQuery, state: FSMContext):
    acc_id = int(callback.data.removeprefix("bcast_acc_toggle_"))
    data = await state.get_data()
    selected = set(data.get("selected_accounts", []))
    selected.symmetric_difference_update({acc_id})
    await state.update_data(selected_accounts=list(selected))
    await callback.message.edit_reply_markup(
        reply_markup=accounts_checkbox_keyboard(data["accounts_list"], selected)
    )
    await callback.answer()


@router.callback_query(
    F.data == "bcast_acc_all", StateFilter(BroadcastStates.selecting_accounts)
)
async def cb_acc_select_all(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    selected = {a["id"] for a in data["accounts_list"]}
    await state.update_data(selected_accounts=list(selected))
    await callback.message.edit_reply_markup(
        reply_markup=accounts_checkbox_keyboard(data["accounts_list"], selected)
    )
    await callback.answer()


@router.callback_query(
    F.data == "bcast_acc_none", StateFilter(BroadcastStates.selecting_accounts)
)
async def cb_acc_deselect_all(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await state.update_data(selected_accounts=[])
    await callback.message.edit_reply_markup(
        reply_markup=accounts_checkbox_keyboard(data["accounts_list"], set())
    )
    await callback.answer()


@router.callback_query(
    F.data == "bcast_acc_confirm", StateFilter(BroadcastStates.selecting_accounts)
)
async def cb_acc_confirm(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    selected_ids = set(data.get("selected_accounts", []))
    if not selected_ids:
        await callback.answer("⚠️ Kamida bitta akkaunt tanlang!", show_alert=True)
        return
    await callback.answer()

    groups = await db.get_all_groups()
    await state.update_data(groups_list=groups, selected_groups=data.get("selected_groups", []), groups_page=0)
    await state.set_state(BroadcastStates.selecting_groups)
    await _render_groups_selection(callback, state, edit_text=True)


@router.callback_query(
    F.data == "bcast_add_group_manual",
    StateFilter(BroadcastStates.selecting_groups, BroadcastStates.adding_group_username),
)
async def cb_add_group_manual(callback: CallbackQuery, state: FSMContext):
    await state.set_state(BroadcastStates.adding_group_username)
    await callback.message.edit_text(
        "✍️ <b>Guruh username yoki havolasini kiriting:</b>\n\n"
        "Misol: <code>@toshkent_taksi</code> yoki <code>https://t.me/toshkent_taksi</code>",
        reply_markup=back_keyboard("bcast_back_to_group_select"),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(
    F.data == "bcast_back_to_group_select",
    StateFilter(BroadcastStates.adding_group_username),
)
async def cb_back_to_group_select(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    groups = await db.get_all_groups()
    await state.update_data(groups_list=groups)
    await state.set_state(BroadcastStates.selecting_groups)
    await _render_groups_selection(callback, state, edit_text=True)
    await callback.answer()


@router.message(StateFilter(BroadcastStates.adding_group_username))
async def msg_add_group_username(message: Message, state: FSMContext):
    username_input = message.text.strip()
    data = await state.get_data()
    selected_acc_ids = set(data.get("selected_accounts", []))
    accounts_list = data.get("accounts_list", [])

    candidate_accs = [a for a in accounts_list if a["id"] in selected_acc_ids and a["is_active"]]
    if not candidate_accs:
        candidate_accs = [a for a in accounts_list if a["is_active"]]
    if not candidate_accs:
        candidate_accs = await db.get_active_accounts()

    if not candidate_accs:
        await message.answer("❌ Faol akkaunt topilmadi. Avval **Akkauntlar -> ➕ Akkaunt qo'shish** bo'limidan akkaunt qo'shing.")
        return

    status_msg = await message.answer(
        f"⏳ <code>{username_input}</code> tekshirilmoqda va guruh ma'lumotlari yuklanmoqda...",
        parse_mode="HTML",
    )

    group_info = None
    last_error = None
    invalid_phones = []

    for acc in candidate_accs:
        try:
            group_info = await tm.add_group_by_username(
                acc["session_string"], acc["phone"], username_input
            )
            if group_info:
                break
        except Exception as e:
            err_str = str(e)
            logger.error(f"add_group_by_username error ({username_input}) on {acc['phone']}: {err_str}")
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
            err_text += f"\n\n⚠️ Sessiyasi bekor qilingan (chiqib ketilgan) akkaunt(lar) bazadan tozalandi: {', '.join(invalid_phones)}. Iltimos, yangi akkaunt qo'shing."
        else:
            err_text += "\n\nUsername yoki havola to'g'riligini va akkaunt bu guruhga kirish huquqiga ega ekanini tekshiring."

        await status_msg.edit_text(
            err_text,
            reply_markup=back_keyboard("bcast_back_to_group_select"),
        )
        return

    await db.save_groups([group_info])

    groups = await db.get_all_groups()
    added_db_group = next(
        (g for g in groups if g["group_id"] == group_info["group_id"]), None
    )

    selected_groups = set(data.get("selected_groups", []))
    if added_db_group:
        selected_groups.add(added_db_group["id"])

    await state.update_data(
        groups_list=groups, selected_groups=list(selected_groups)
    )
    await state.set_state(BroadcastStates.selecting_groups)

    try:
        await status_msg.delete()
    except Exception:
        pass

    await message.answer(
        f"✅ <b>{group_info['title']}</b> guruhi muvaffaqiyatli qo'shildi va tanlandi!",
        parse_mode="HTML",
    )

    fake_cb = CallbackQuery(
        id="",
        from_user=message.from_user,
        chat_instance="",
        message=await message.answer("🏘 Guruhlarni tanlang:"),
    )
    await _render_groups_selection(fake_cb, state, edit_text=True)


@router.callback_query(
    F.data == "bcast_select_accounts", StateFilter(BroadcastStates.selecting_groups)
)
async def cb_back_to_accounts(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    selected = set(data.get("selected_accounts", []))
    await state.set_state(BroadcastStates.selecting_accounts)
    await callback.message.edit_text(
        "👥 Xabar yuboradigan akkauntlarni tanlang:",
        reply_markup=accounts_checkbox_keyboard(data["accounts_list"], selected),
    )
    await callback.answer()


@router.callback_query(
    F.data.startswith("bcast_grp_toggle_"),
    StateFilter(BroadcastStates.selecting_groups),
)
async def cb_toggle_group(callback: CallbackQuery, state: FSMContext):
    grp_id = int(callback.data.removeprefix("bcast_grp_toggle_"))
    data = await state.get_data()
    selected = set(data.get("selected_groups", []))
    selected.symmetric_difference_update({grp_id})
    await state.update_data(selected_groups=list(selected))
    await _render_groups_selection(callback, state)
    await callback.answer()


@router.callback_query(
    F.data.startswith("bcast_grp_page_"),
    StateFilter(BroadcastStates.selecting_groups),
)
async def cb_change_groups_page(callback: CallbackQuery, state: FSMContext):
    page_token = callback.data.removeprefix("bcast_grp_page_")
    if page_token == "keep":
        await callback.answer()
        return

    data = await state.get_data()
    groups = data.get("groups_list", [])
    current_page = _clamp_groups_page(int(data.get("groups_page", 0)), len(groups))
    page = _clamp_groups_page(int(page_token), len(groups))
    if page == current_page:
        await callback.answer()
        return
    await state.update_data(groups_page=page)
    await _render_groups_selection(callback, state)
    await callback.answer()


@router.callback_query(
    F.data == "bcast_grp_all", StateFilter(BroadcastStates.selecting_groups)
)
async def cb_grp_select_all(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    selected = {g["id"] for g in data["groups_list"]}
    await state.update_data(selected_groups=list(selected))
    await _render_groups_selection(callback, state)
    await callback.answer()


@router.callback_query(
    F.data == "bcast_grp_none", StateFilter(BroadcastStates.selecting_groups)
)
async def cb_grp_deselect_all(callback: CallbackQuery, state: FSMContext):
    await state.update_data(selected_groups=[])
    await _render_groups_selection(callback, state)
    await callback.answer()


@router.callback_query(
    F.data == "bcast_grp_confirm", StateFilter(BroadcastStates.selecting_groups)
)
async def cb_grp_confirm(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    selected = set(data.get("selected_groups", []))
    if not selected:
        await callback.answer("⚠️ Kamida bitta guruh tanlang!", show_alert=True)
        return

    interval = int(data.get("interval_minutes", 6))
    await state.update_data(interval_minutes=interval)
    await state.set_state(BroadcastStates.selecting_interval)

    await callback.message.edit_text(
        "⏱ <b>Akkauntlar orasidagi intervalni tanlang (minutda):</b>\n\n"
        "Tugmalar orqali intervalni o'zgartiring yoki chatda minut sonini yozib yuborishingiz mumkin:",
        reply_markup=interval_keyboard(interval),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(
    F.data == "bcast_select_groups", StateFilter(BroadcastStates.selecting_interval)
)
async def cb_back_to_groups(callback: CallbackQuery, state: FSMContext):
    await state.set_state(BroadcastStates.selecting_groups)
    await _render_groups_selection(callback, state, edit_text=True)
    await callback.answer()


@router.callback_query(
    F.data.startswith("bcast_intstep_"),
    StateFilter(BroadcastStates.selecting_interval),
)
async def cb_adjust_interval_minutes(callback: CallbackQuery, state: FSMContext):
    action = callback.data.removeprefix("bcast_intstep_")
    if action == "noop":
        await callback.answer()
        return

    data = await state.get_data()
    current = int(data.get("interval_minutes", 6))

    if action == "confirm":
        stagger = int(data.get("stagger_seconds", 60))
        await state.set_state(BroadcastStates.selecting_stagger)
        await callback.message.edit_text(
            f"✅ Interval <b>{current} minut</b> qilib belgilandi!\n\n"
            "⏱ Guruhlar orasidagi kutish vaqtini tanlang <i>(har bir guruhga xabar orasidagi interval)</i>:",
            reply_markup=stagger_keyboard(stagger),
            parse_mode="HTML",
        )
        await callback.answer()
        return

    delta = int(action)
    new_val = max(1, current + delta)

    if new_val == current:
        await callback.answer()
        return

    await state.update_data(interval_minutes=new_val)
    await callback.message.edit_reply_markup(
        reply_markup=interval_keyboard(new_val)
    )
    await callback.answer()


@router.message(StateFilter(BroadcastStates.selecting_interval))
async def msg_custom_interval(message: Message, state: FSMContext):
    text = message.text.strip()
    if not text.isdigit() or int(text) <= 0:
        await message.answer(
            "⚠️ Iltimos, intervalni musbat butun son sifatida kiriting (masalan: <b>6</b> yoki <b>15</b>).",
            parse_mode="HTML"
        )
        return

    interval = int(text)
    stagger = int((await state.get_data()).get("stagger_seconds", 60))
    await state.update_data(interval_minutes=interval, stagger_seconds=stagger)
    await state.set_state(BroadcastStates.selecting_stagger)
    await message.answer(
        f"✅ Interval <b>{interval} minut</b> qilib belgilandi!\n\n"
        "⏱ Guruhlar orasidagi kutish vaqtini tanlang <i>(har bir guruhga xabar orasidagi interval)</i>:",
        reply_markup=stagger_keyboard(stagger),
        parse_mode="HTML",
    )


@router.callback_query(
    F.data == "bcast_select_interval", StateFilter(BroadcastStates.selecting_stagger)
)
async def cb_back_to_interval(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    interval = int(data.get("interval_minutes", 6))
    await state.set_state(BroadcastStates.selecting_interval)
    await callback.message.edit_text(
        "⏱ <b>Akkauntlar orasidagi intervalni tanlang (minutda):</b>\n\n"
        "Tugmalar orqali intervalni o'zgartiring yoki chatda minut sonini yozib yuborishingiz mumkin:",
        reply_markup=interval_keyboard(interval),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(
    F.data.startswith("bcast_stagger_"),
    StateFilter(BroadcastStates.selecting_stagger),
)
async def cb_adjust_stagger(callback: CallbackQuery, state: FSMContext):
    action = callback.data.removeprefix("bcast_stagger_")
    if action == "noop":
        await callback.answer()
        return
    if action == "confirm":
        data = await state.get_data()
        selected_accounts = list(data.get("selected_accounts", []))
        selected_groups = list(data.get("selected_groups", []))
        message_text = data.get("message_text", "")
        interval = data.get("interval_minutes", 10)
        stagger = data.get("stagger_seconds", 60)
        task_id = await db.create_broadcast_task(
            message_text, selected_accounts, selected_groups, interval, stagger
        )
        await state.clear()
        text = (
            f"✅ <b>Tarqatish yaratildi!</b>\n\n"
            f"🆔 ID: <code>{task_id}</code>\n"
            f"👥 Akkauntlar: {len(selected_accounts)} ta\n"
            f"🏘 Guruhlar: {len(selected_groups)} ta\n"
            f"⏱ Interval: {interval} daqiqa\n"
            f"⏳ Stagger: {stagger} sek\n"
            f"📊 Holat: 🔴 To'xtatilgan\n\n"
            f"Boshlash uchun ▶️ tugmasini bosing."
        )
        await callback.message.edit_text(
            text,
            reply_markup=broadcast_control_keyboard(task_id, "stopped"),
            parse_mode="HTML",
        )
        await callback.answer()
        return
    delta = int(action)
    data = await state.get_data()
    current = data.get("stagger_seconds", 60)
    new_val = max(1, current + delta)
    await state.update_data(stagger_seconds=new_val)
    await callback.message.edit_reply_markup(
        reply_markup=stagger_keyboard(new_val)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("bcast_delete_") & ~F.data.startswith("bcast_delete_confirm_"))
async def cb_bcast_delete(callback: CallbackQuery):
    task_id = int(callback.data.removeprefix("bcast_delete_"))
    task = await db.get_broadcast_task(task_id)
    if not task:
        await callback.answer("Tarqatish topilmadi.", show_alert=True)
        return
    await callback.message.edit_text(
        f"🗑 <b>Tarqatish #{task_id}</b>ni o'chirishni tasdiqlaysizmi?",
        reply_markup=broadcast_confirm_delete_keyboard(task_id),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("bcast_delete_confirm_"))
async def cb_bcast_delete_confirm(callback: CallbackQuery, broadcast_manager: BroadcastManager):
    task_id = int(callback.data.removeprefix("bcast_delete_confirm_"))
    await broadcast_manager.stop(task_id)
    await db.delete_broadcast_task(task_id)
    tasks = await db.get_all_broadcast_tasks()
    if not tasks:
        await callback.message.edit_text(
            "📋 Hozircha tarqatishlar yo'q.",
            reply_markup=back_keyboard("menu_broadcast"),
        )
    else:
        await callback.message.edit_text(
            f"📋 <b>Tarqatishlar ro'yxati</b> ({len(tasks)} ta):",
            reply_markup=broadcast_list_keyboard(tasks),
            parse_mode="HTML",
        )
    await callback.answer("🗑 O'chirildi!", show_alert=True)


@router.callback_query(F.data == "bcast_list")
async def cb_bcast_list(callback: CallbackQuery):
    tasks = await db.get_all_broadcast_tasks()
    if not tasks:
        await callback.message.edit_text(
            "📋 Hozircha tarqatishlar yo'q.",
            reply_markup=back_keyboard("menu_broadcast"),
        )
    else:
        await callback.message.edit_text(
            f"📋 <b>Tarqatishlar ro'yxati</b> ({len(tasks)} ta):",
            reply_markup=broadcast_list_keyboard(tasks),
            parse_mode="HTML",
        )
    await callback.answer()


@router.callback_query(F.data.startswith("bcast_view_"))
async def cb_bcast_view(callback: CallbackQuery):
    task_id = int(callback.data.removeprefix("bcast_view_"))
    task = await db.get_broadcast_task(task_id)
    if not task:
        await callback.answer("Tarqatish topilmadi.", show_alert=True)
        return
    await _render_broadcast_task(callback, task_id, task)
    await callback.answer()


@router.callback_query(F.data.startswith("bcast_stats_"))
async def cb_bcast_stats(callback: CallbackQuery, broadcast_manager: BroadcastManager):
    task_id = int(callback.data.removeprefix("bcast_stats_"))
    task = await db.get_broadcast_task(task_id)
    if not task:
        await callback.answer("Tarqatish topilmadi.", show_alert=True)
        return

    account_ids = json.loads(task["account_ids"])
    accounts = []
    for acc_id in account_ids:
        acc = await db.get_account_by_id(acc_id)
        if acc:
            accounts.append(acc)

    stats = broadcast_manager.get_account_stats(task_id, accounts)
    text = _build_stats_text(task_id, task, stats)

    await callback.message.edit_text(
        text,
        reply_markup=broadcast_stats_keyboard(task_id),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("bcast_start_"))
async def cb_bcast_start(callback: CallbackQuery, broadcast_manager: BroadcastManager):
    task_id = int(callback.data.removeprefix("bcast_start_"))
    await broadcast_manager.start(task_id)
    task = await db.get_broadcast_task(task_id)
    if not task:
        await callback.answer("Tarqatish topilmadi.", show_alert=True)
        return
    await _render_broadcast_task(callback, task_id, task)
    await callback.answer("▶️ Tarqatish boshlandi!", show_alert=True)


@router.callback_query(F.data.startswith("bcast_pause_"))
async def cb_bcast_pause(callback: CallbackQuery, broadcast_manager: BroadcastManager):
    task_id = int(callback.data.removeprefix("bcast_pause_"))
    await broadcast_manager.pause(task_id)
    task = await db.get_broadcast_task(task_id)
    if not task:
        await callback.answer("Tarqatish topilmadi.", show_alert=True)
        return
    await _render_broadcast_task(callback, task_id, task)
    await callback.answer("⏸ To'xtatildi!", show_alert=True)


@router.callback_query(F.data.startswith("bcast_resume_"))
async def cb_bcast_resume(callback: CallbackQuery, broadcast_manager: BroadcastManager):
    task_id = int(callback.data.removeprefix("bcast_resume_"))
    await broadcast_manager.resume(task_id)
    task = await db.get_broadcast_task(task_id)
    if not task:
        await callback.answer("Tarqatish topilmadi.", show_alert=True)
        return
    await _render_broadcast_task(callback, task_id, task)
    await callback.answer("▶️ Davom ettirildi!", show_alert=True)


@router.callback_query(F.data.startswith("bcast_stop_"))
async def cb_bcast_stop(callback: CallbackQuery, broadcast_manager: BroadcastManager):
    task_id = int(callback.data.removeprefix("bcast_stop_"))
    await broadcast_manager.stop(task_id)
    task = await db.get_broadcast_task(task_id)
    if not task:
        await callback.answer("Tarqatish topilmadi.", show_alert=True)
        return
    await _render_broadcast_task(callback, task_id, task)
    await callback.answer("🛑 Yakunlandi!", show_alert=True)