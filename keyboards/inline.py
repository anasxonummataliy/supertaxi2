from aiogram.utils.keyboard import InlineKeyboardBuilder


def main_menu_keyboard():
    b = InlineKeyboardBuilder()
    b.button(text="👤 Akkauntlar", callback_data="menu_accounts")
    b.button(text="🏘 Guruhlar", callback_data="menu_groups")
    b.button(text="📢 Xabar tarqatish", callback_data="menu_broadcast")
    b.adjust(1)
    return b.as_markup()


def groups_menu_keyboard():
    b = InlineKeyboardBuilder()
    b.button(text="➕ Guruh qo'shish (username)", callback_data="group_add_username")
    b.button(text="📋 Guruhlar ro'yxati", callback_data="group_list")
    b.button(text="🗑 Barcha guruhlarni o'chirish", callback_data="group_clear_all")
    b.button(text="🔙 Orqaga", callback_data="menu_main")
    b.adjust(1)
    return b.as_markup()


def group_list_keyboard(groups: list):
    b = InlineKeyboardBuilder()
    for g in groups:
        title = g["title"][:30]
        un = f" (@{g['username']})" if g.get("username") else ""
        b.button(text=f"🏘 {title}{un}", callback_data=f"group_view_{g['id']}")
    b.button(text="🗑 Barcha guruhlarni o'chirish", callback_data="group_clear_all")
    b.button(text="🔙 Orqaga", callback_data="menu_groups")
    b.adjust(1)
    return b.as_markup()


def group_detail_keyboard(group_db_id: int):
    b = InlineKeyboardBuilder()
    b.button(text="🗑 O'chirish", callback_data=f"group_delete_{group_db_id}")
    b.button(text="🔙 Orqaga", callback_data="group_list")
    b.adjust(1)
    return b.as_markup()


def accounts_menu_keyboard():
    b = InlineKeyboardBuilder()
    b.button(text="➕ Akkaunt qo'shish", callback_data="account_add")
    b.button(text="📋 Akkauntlar ro'yxati", callback_data="account_list")
    b.button(text="🔙 Orqaga", callback_data="menu_main")
    b.adjust(1)
    return b.as_markup()


def account_add_method_keyboard():
    b = InlineKeyboardBuilder()
    b.button(text="📱 Telefon kodi", callback_data="account_add_phone")
    b.button(text="🔳 QR login", callback_data="account_add_qr")
    b.button(text="🔙 Orqaga", callback_data="menu_accounts")
    b.adjust(1)
    return b.as_markup()


def back_keyboard(cb: str = "menu_main"):
    b = InlineKeyboardBuilder()
    b.button(text="🔙 Orqaga", callback_data=cb)
    return b.as_markup()


def account_qr_keyboard():
    b = InlineKeyboardBuilder()
    b.button(text="🔄 Yangi QR", callback_data="account_qr_refresh")
    b.button(text="❌ Bekor qilish", callback_data="account_qr_cancel")
    b.adjust(2)
    return b.as_markup()


def account_code_keyboard():
    b = InlineKeyboardBuilder()
    b.button(text="🔄 Kodni qayta yuborish", callback_data="account_code_resend")
    b.button(text="❌ Bekor qilish", callback_data="account_code_cancel")
    b.adjust(1)
    return b.as_markup()


def account_list_keyboard(accounts: list):
    b = InlineKeyboardBuilder()
    for acc in accounts:
        mark = "✅" if acc["is_active"] else "❌"
        b.button(text=f"{mark} {acc['phone']}", callback_data=f"account_view_{acc['id']}")
    b.button(text="🔙 Orqaga", callback_data="menu_accounts")
    b.adjust(1)
    return b.as_markup()


def account_detail_keyboard(account_id: int):
    b = InlineKeyboardBuilder()
    b.button(text="🗑 O'chirish", callback_data=f"account_delete_{account_id}")
    b.button(text="🔙 Orqaga", callback_data="account_list")
    b.adjust(1)
    return b.as_markup()


def confirm_delete_keyboard(account_id: int):
    b = InlineKeyboardBuilder()
    b.button(text="✅ Ha, o'chirish", callback_data=f"account_delete_confirm_{account_id}")
    b.button(text="❌ Bekor qilish", callback_data=f"account_view_{account_id}")
    b.adjust(2)
    return b.as_markup()


def accounts_checkbox_keyboard(accounts: list, selected: set):
    b = InlineKeyboardBuilder()
    for acc in accounts:
        mark = "✅" if acc["id"] in selected else "☐"
        b.button(
            text=f"{mark} {acc['phone']}",
            callback_data=f"bcast_acc_toggle_{acc['id']}",
        )
    b.button(text="☑️ Hammasini tanlash", callback_data="bcast_acc_all")
    b.button(text="🔲 Hammasini bekor", callback_data="bcast_acc_none")
    b.button(text="➡️ Tasdiqlash", callback_data="bcast_acc_confirm")
    b.button(text="🔙 Bekor qilish", callback_data="menu_broadcast")
    b.adjust(1)
    return b.as_markup()


def groups_checkbox_keyboard(
    groups: list, selected: set, page: int = 0, page_size: int = 10
):
    b = InlineKeyboardBuilder()
    total_pages = max(1, (len(groups) + page_size - 1) // page_size)
    page = min(max(page, 0), total_pages - 1)
    start = page * page_size
    end = start + page_size
    page_groups = groups[start:end]

    for grp in page_groups:
        mark = "✅" if grp["id"] in selected else "☐"
        b.button(
            text=f"{mark} {grp['title'][:35]}",
            callback_data=f"bcast_grp_toggle_{grp['id']}",
        )

    if total_pages > 1:
        prev_callback = (
            "bcast_grp_page_keep" if page == 0 else f"bcast_grp_page_{page - 1}"
        )
        next_callback = (
            "bcast_grp_page_keep"
            if page >= total_pages - 1
            else f"bcast_grp_page_{page + 1}"
        )
        b.button(text="◀️", callback_data=prev_callback)
        b.button(text=f"{page + 1}/{total_pages}", callback_data="bcast_grp_page_keep")
        b.button(text="▶️", callback_data=next_callback)

    b.button(text="➕ Guruh qo'shish (username)", callback_data="bcast_add_group_manual")
    b.button(text="☑️ Hammasini tanlash", callback_data="bcast_grp_all")
    b.button(text="🔲 Hammasini bekor", callback_data="bcast_grp_none")
    b.button(text="➡️ Tasdiqlash", callback_data="bcast_grp_confirm")
    b.button(text="🔙 Orqaga", callback_data="bcast_select_accounts")
    layout = [1] * len(page_groups)
    if total_pages > 1:
        layout.append(3)
    layout.extend([1, 1, 1, 1, 1])
    b.adjust(*layout)
    return b.as_markup()


def interval_keyboard(minutes: int = 6):
    b = InlineKeyboardBuilder()
    b.button(text="-10", callback_data="bcast_intstep_-10")
    b.button(text="-1", callback_data="bcast_intstep_-1")
    b.button(text=f"⏱ {minutes} daqiqa", callback_data="bcast_intstep_noop")
    b.button(text="+1", callback_data="bcast_intstep_+1")
    b.button(text="+10", callback_data="bcast_intstep_+10")
    b.button(text="✅ Tasdiqlash", callback_data="bcast_intstep_confirm")
    b.button(text="🔙 Orqaga", callback_data="bcast_select_groups")
    b.adjust(5, 1, 1)
    return b.as_markup()


def stagger_keyboard(seconds: int = 30):
    b = InlineKeyboardBuilder()
    b.button(text="-30s", callback_data="bcast_stagger_-30")
    b.button(text="-10s", callback_data="bcast_stagger_-10")
    b.button(text=f"⏳ {seconds} sek", callback_data="bcast_stagger_noop")
    b.button(text="+10s", callback_data="bcast_stagger_+10")
    b.button(text="+30s", callback_data="bcast_stagger_+30")

    b.button(text="-5s", callback_data="bcast_stagger_-5")
    b.button(text="-1s", callback_data="bcast_stagger_-1")
    b.button(text="🔄 30s", callback_data="bcast_stagger_set30")
    b.button(text="+1s", callback_data="bcast_stagger_+1")
    b.button(text="+5s", callback_data="bcast_stagger_+5")

    b.button(text="✅ Tasdiqlash", callback_data="bcast_stagger_confirm")
    b.button(text="🔙 Orqaga", callback_data="bcast_select_interval")
    b.adjust(5, 5, 1, 1)
    return b.as_markup()


def broadcast_confirm_delete_keyboard(task_id: int):
    b = InlineKeyboardBuilder()
    b.button(text="✅ Ha, o'chirish", callback_data=f"bcast_delete_confirm_{task_id}")
    b.button(text="❌ Bekor qilish", callback_data=f"bcast_view_{task_id}")
    b.adjust(2)
    return b.as_markup()


def broadcast_menu_keyboard():
    b = InlineKeyboardBuilder()
    b.button(text="➕ Yangi tarqatish", callback_data="bcast_new")
    b.button(text="📋 Tarqatishlar ro'yxati", callback_data="bcast_list")
    b.button(text="🔙 Orqaga", callback_data="menu_main")
    b.adjust(1)
    return b.as_markup()


def broadcast_control_keyboard(task_id: int, status: str):
    b = InlineKeyboardBuilder()
    if status == "running":
        b.button(text="⏸ To'xtatish", callback_data=f"bcast_pause_{task_id}")
        b.button(text="🛑 Yakunlash", callback_data=f"bcast_stop_{task_id}")
    elif status == "paused":
        b.button(text="▶️ Davom ettirish", callback_data=f"bcast_resume_{task_id}")
        b.button(text="🛑 Yakunlash", callback_data=f"bcast_stop_{task_id}")
    else:
        b.button(text="▶️ Boshlash", callback_data=f"bcast_start_{task_id}")
        b.button(text="🗑 O'chirish", callback_data=f"bcast_delete_{task_id}")
    b.button(text="📊 Statistika", callback_data=f"bcast_stats_{task_id}")
    b.button(text="🔙 Ro'yxatga", callback_data="bcast_list")
    b.adjust(2)
    return b.as_markup()


def broadcast_stats_keyboard(task_id: int):
    b = InlineKeyboardBuilder()
    b.button(text="🔄 Yangilash", callback_data=f"bcast_stats_{task_id}")
    b.button(text="🔙 Orqaga", callback_data=f"bcast_view_{task_id}")
    b.adjust(2)
    return b.as_markup()


def broadcast_list_keyboard(tasks: list):
    b = InlineKeyboardBuilder()
    emoji_map = {"running": "🟢", "paused": "🟡", "stopped": "🔴"}
    for t in tasks:
        e = emoji_map.get(t["status"], "⚪")
        interval_min = t.get("interval_minutes", 6)
        stagger_sec = t.get("stagger_seconds", 30)
        b.button(
            text=f"{e} #{t['id']} | {interval_min}daq ({stagger_sec}s)",
            callback_data=f"bcast_view_{t['id']}",
        )
    b.button(text="🔙 Orqaga", callback_data="menu_broadcast")
    b.adjust(1)
    return b.as_markup()