import asyncio
import json
import logging
import time
from datetime import datetime
from database import db
from services import telethon_manager as tm

import html
import random
import re
from telethon import errors

logger = logging.getLogger(__name__)

_POLL_INTERVAL = 5.0

# Ko'rinmas belgilar (har bir yuborilgan xabarni Telegram filtrlari uchun avtomatik noyob/unique qilish)
_ZERO_WIDTH_CHARS = ["\u200b", "\u200c", "\u200d", "\ufeff"]


def apply_anti_flood_variation(text: str) -> str:
    """Foydalanuvchining oddiy matniga orqa fonda avtomatik ko'rinmas belgilar qo'shib har safar yangi hash yaratadi."""
    if not text:
        return text
    # 1 dan 4 tagacha tasodifiy ko'rinmas belgilar qo'shiladi (foydalanuvchiga umuman ko'rinmaydi)
    invisible_salt = "".join(random.choices(_ZERO_WIDTH_CHARS, k=random.randint(1, 4)))
    return f"{text}{invisible_salt}"


def _format_send_error(e: Exception) -> str:
    err_str = str(e)
    err_lower = err_str.lower()
    cls_name = type(e).__name__.lower()

    # 1. SlowModeWait (Guruhda Sekin rejim yoqilgan)
    if (
        isinstance(e, errors.SlowModeWaitError)
        or "slowmode" in err_lower
        or "slowmode" in cls_name
        or "before sending another message in this chat" in err_lower
    ):
        sec = getattr(e, "seconds", None)
        if sec is None:
            m = re.search(r"(\d+)\s*seconds?", err_str, re.IGNORECASE)
            if m:
                sec = int(m.group(1))
        if sec is not None:
            mins, s = divmod(int(sec), 60)
            wait_text = f"{mins} daqiqa {s} soniya" if mins else f"{s} soniya"
            return f"Guruhda sekin rejim (Slow Mode) yoqilgan: yana {wait_text} kutish kerak"
        return "Guruhda sekin rejim (Slow Mode) yoqilgan, belgilangan vaqt o'tmaguncha xabar yozib bo'lmaydi"

    # 2. FloodWait (Telegram cheklovi)
    if (
        isinstance(e, errors.FloodWaitError)
        or "floodwait" in err_lower
        or "floodwait" in cls_name
        or "flood wait" in err_lower
    ):
        sec = getattr(e, "seconds", None)
        if sec is None:
            m = re.search(r"(\d+)\s*seconds?", err_str, re.IGNORECASE)
            if m:
                sec = int(m.group(1))
        if sec is not None:
            mins, s = divmod(int(sec), 60)
            wait_text = f"{mins} daqiqa {s} soniya" if mins else f"{s} soniya"
            return f"Telegram cheklovi (FloodWait): yana {wait_text} kutish kerak"
        return "Telegram cheklovi (FloodWait: biroz kutish kerak)"

    # 3. Guruhda yozish ruxsati yo'qligi (ChatWriteForbiddenError / You can't write in this chat)
    if (
        isinstance(e, getattr(errors, "ChatWriteForbiddenError", Exception))
        or "chatwriteforbidden" in err_lower
        or "chatwriteforbidden" in cls_name
        or "can't write in this chat" in err_lower
        or "cannot write in this chat" in err_lower
        or "cannot write" in err_lower
        or "can't write" in err_lower
        or "write forbidden" in err_lower
        or "chat_write_forbidden" in err_lower
    ):
        return "Guruhda a'zolarga xabar yozish ruxsati yo'q (yozish yopilgan yoki cheklangan)"

    # 4. Guruhga a'zo bo'lmagani uchun yozib bo'lmasligi
    if (
        isinstance(e, getattr(errors, "ChatGuestSendForbiddenError", Exception))
        or "chatguestsendforbidden" in err_lower
        or "must join this channel" in err_lower
        or "must join" in err_lower
    ):
        return "Guruhga xabar yuborishdan oldin unga a'zo bo'lish talab etiladi"

    # 5. Faqat adminlar yozishi mumkin bo'lgan guruh/kanal
    if (
        isinstance(e, getattr(errors, "ChatAdminRequiredError", Exception))
        or "chatadminrequired" in err_lower
        or "admin privileges are required" in err_lower
        or "chat_admin_required" in err_lower
    ):
        return "Bu guruhga faqat adminlar xabar yoza oladi (Admin ruxsati kerak)"

    # 6. Akkaunt guruhda bloklangan (Ban / Restricted)
    if (
        isinstance(e, getattr(errors, "UserBannedInChannelError", Exception))
        or isinstance(e, getattr(errors, "ChatRestrictedError", Exception))
        or "userbannedinchannel" in err_lower
        or "chatrestricted" in err_lower
        or "you're banned" in err_lower
        or "banned from sending messages" in err_lower
        or "restricted from sending" in err_lower
        or "user_banned_in_channel" in err_lower
    ):
        return "Akkaunt bu guruhda bloklangan (admin tomonidan ban yoki cheklov qo'yilgan)"

    # 7. Akkaunt Telegram tomonidan butunlay bloklangan yoki o'chirilgan
    if (
        isinstance(e, getattr(errors, "UserDeactivatedBanError", Exception))
        or isinstance(e, getattr(errors, "PhoneNumberBannedError", Exception))
        or "userdeactivatedban" in err_lower
        or "phonenumberbanned" in err_lower
        or "user_deactivated_ban" in err_lower
        or "phone_number_banned" in err_lower
    ):
        return "Akkaunt Telegram tomonidan bloklangan (Spam / Ban)"

    # 8. Sessiya bekor qilingan / chiqib ketilgan
    if (
        isinstance(e, getattr(errors, "SessionPasswordNeededError", Exception))
        or isinstance(e, getattr(errors, "SessionRevokedError", Exception))
        or isinstance(e, getattr(errors, "AuthKeyUnregisteredError", Exception))
        or isinstance(e, getattr(errors, "AuthKeyDuplicatedError", Exception))
        or "authorization has been invalidated" in err_lower
        or "deauthorized" in err_lower
        or "session_revoked" in err_lower
        or "session_expired" in err_lower
        or "sessionpasswordneeded" in err_lower
        or "auth_key_unregistered" in err_lower
        or "authkeyunregistered" in err_lower
        or ("session" in err_lower and ("invalid" in err_lower or "revoked" in err_lower or "expired" in err_lower))
    ):
        return "Akkaunt sessiyasi bekor qilingan (chiqib ketilgan yoki 2FA o'zgargan)"

    # 9. Guruh topilmadi / Private / Kirish imkoni yo'q
    if (
        isinstance(e, getattr(errors, "ChannelPrivateError", Exception))
        or isinstance(e, getattr(errors, "ChannelInvalidError", Exception))
        or isinstance(e, getattr(errors, "PeerIdInvalidError", Exception))
        or "channelprivate" in err_lower
        or "channel_private" in err_lower
        or "chatidinvalid" in err_lower
        or "peeridinvalid" in err_lower
        or "the channel is private" in err_lower
        or "could not find" in err_lower
        or "entity not found" in err_lower
    ):
        return "Guruh topilmadi, yopiq (maxfiy) yoki unga kirish imkoni yo'q"

    # 10. Xabar matni limiti yoki formati xatosi
    if "messagetoolong" in err_lower or "message is too long" in err_lower or "message_too_long" in err_lower:
        return "Xabar matni juda uzun (Telegram limiti 4096 ta belgi)"

    if "messageempty" in err_lower or "message is empty" in err_lower or "message_empty" in err_lower:
        return "Xabar matni bo'sh bo'lishi mumkin emas"

    # 11. Tarmoq va timeout xatoliklari
    if "timeout" in err_lower or "timed out" in err_lower or "connection" in err_lower:
        return "Internet yoki Telegram serveri bilan ulanishda vaqtinchalik uzilish (Timeout)"

    # Boshqa Telethon xatoliklari bo'lsa, "(caused by ...)" texnik qismini olib tashlab toza chiqarish
    clean_msg = err_str
    if "(caused by" in clean_msg:
        clean_msg = clean_msg.split("(caused by")[0].strip()

    return f"Telegram xatoligi: {clean_msg}"


class BroadcastManager:
    def __init__(self, bot=None):
        self.bot = bot
        self._tasks: dict[int, asyncio.Task] = {}
        self._next_send_time: dict[int, dict[int, float]] = {}
        self._last_sent_time: dict[int, dict[int, float]] = {}

    async def _notify_admins(self, text: str):
        if not self.bot:
            return
        import os
        raw = os.getenv("ADMIN_IDS", "")
        admin_ids = [int(x.strip()) for x in raw.split(",") if x.strip().isdigit()]
        for admin_id in admin_ids:
            try:
                await self.bot.send_message(admin_id, text, parse_mode="HTML")
            except Exception as ex:
                logger.warning(f"Admin {admin_id} ga xabar yuborishda xatolik: {ex}")

    def _mono_to_wall(self, mono: float) -> datetime:
        wall = time.time() + (mono - asyncio.get_event_loop().time())
        return datetime.fromtimestamp(wall)

    async def get_account_stats(self, task_id: int, accounts: list[dict]) -> list[dict]:
        schedule = self._next_send_time.get(task_id, {})
        last_sent = self._last_sent_time.get(task_id, {})
        db_last_sent = await db.get_broadcast_account_last_sent(task_id)
        now_mono = asyncio.get_event_loop().time()
        result = []
        for acc in accounts:
            acc_id = acc["id"]
            next_mono = schedule.get(acc_id)

            if next_mono is not None:
                remaining_sec = max(0.0, next_mono - now_mono)
                next_dt = self._mono_to_wall(next_mono)
            else:
                remaining_sec = None
                next_dt = None

            last_dt = None
            if acc_id in last_sent:
                last_dt = self._mono_to_wall(last_sent[acc_id])
            elif acc_id in db_last_sent and db_last_sent[acc_id]:
                try:
                    last_dt = datetime.fromisoformat(db_last_sent[acc_id])
                except Exception:
                    last_dt = None

            result.append({
                "phone": acc["phone"],
                "is_active": acc["is_active"],
                "last_sent": last_dt,
                "next_send": next_dt,
                "remaining_sec": remaining_sec,
            })
        return result

    async def start(self, task_id: int):
        await db.update_broadcast_status(task_id, "running")
        if task_id in self._tasks and not self._tasks[task_id].done():
            return
        self._next_send_time.pop(task_id, None)
        task = asyncio.create_task(
            self._broadcast_loop(task_id), name=f"broadcast_{task_id}"
        )
        self._tasks[task_id] = task
        logger.info(f"Broadcast {task_id} boshlandi")

    async def pause(self, task_id: int):
        await db.update_broadcast_status(task_id, "paused")
        logger.info(f"Broadcast {task_id} to'xtatildi")

    async def resume(self, task_id: int):
        await db.update_broadcast_status(task_id, "running")
        logger.info(f"Broadcast {task_id} davom ettirildi")

    async def stop(self, task_id: int):
        await db.update_broadcast_status(task_id, "stopped")
        if task_id in self._tasks and not self._tasks[task_id].done():
            self._tasks[task_id].cancel()
            try:
                await self._tasks[task_id]
            except asyncio.CancelledError:
                pass
        self._tasks.pop(task_id, None)
        self._next_send_time.pop(task_id, None)
        logger.info(f"Broadcast {task_id} yakunlandi")

    async def _broadcast_loop(self, task_id: int):
        schedule: dict[int, float] = self._next_send_time.setdefault(task_id, {})
        last_sent: dict[int, float] = self._last_sent_time.setdefault(task_id, {})

        try:
            while True:
                task_data = await db.get_broadcast_task(task_id)
                if not task_data or task_data["status"] == "stopped":
                    break

                if task_data["status"] == "paused":
                    await asyncio.sleep(_POLL_INTERVAL)
                    continue

                account_ids = json.loads(task_data["account_ids"])
                group_ids = json.loads(task_data["group_ids"])
                cycle_sec = task_data.get("interval_minutes", 6) * 60
                stagger_sec = task_data.get("stagger_seconds", 30)
                message_text = task_data["message_text"]

                accounts: list[dict] = []
                for acc_id in account_ids:
                    acc = await db.get_account_by_id(acc_id)
                    if acc and acc["is_active"]:
                        accounts.append(acc)

                groups: list[dict] = []
                for grp_id in group_ids:
                    grp = await db.get_group_by_id(grp_id)
                    if grp:
                        groups.append(grp)

                if not accounts or not groups:
                    logger.warning(
                        f"Broadcast {task_id}: akkaunt yoki guruh yo'q, 30s kutilmoqda"
                    )
                    await asyncio.sleep(30)
                    continue

                # Remove inactive/removed accounts from schedule
                active_ids = {acc["id"] for acc in accounts}
                for dead_id in list(schedule.keys()):
                    if dead_id not in active_ids:
                        schedule.pop(dead_id, None)

                now = asyncio.get_event_loop().time()

                # Initialize schedule for new accounts with stagger_sec spacing
                for idx, acc in enumerate(accounts):
                    if acc["id"] not in schedule:
                        if not schedule:
                            schedule[acc["id"]] = now
                        else:
                            schedule[acc["id"]] = max(schedule.values()) + stagger_sec

                # Find due accounts sorted by scheduled time
                due_accounts = [
                    acc for acc in accounts
                    if schedule.get(acc["id"], float("inf")) <= asyncio.get_event_loop().time()
                ]
                due_accounts.sort(key=lambda acc: schedule.get(acc["id"], 0))

                if not due_accounts:
                    earliest = min(schedule[acc["id"]] for acc in accounts)
                    wait = min(max(earliest - asyncio.get_event_loop().time(), 0.1), _POLL_INTERVAL)
                    await asyncio.sleep(wait)
                    continue

                account = due_accounts[0]

                status_check = await db.get_broadcast_task(task_id)
                if not status_check or status_check["status"] == "stopped":
                    return

                while status_check and status_check["status"] == "paused":
                    await asyncio.sleep(_POLL_INTERVAL)
                    status_check = await db.get_broadcast_task(task_id)
                    if not status_check or status_check["status"] == "stopped":
                        return

                logger.info(
                    f"[{task_id}] {account['phone']} barcha tanlangan guruhlarga ({len(groups)} ta) xabar yuborishni boshladi..."
                )

                # Send message to all groups for this account in one continuous batch
                for group in groups:
                    # Check task status before each group
                    curr_task = await db.get_broadcast_task(task_id)
                    if not curr_task or curr_task["status"] == "stopped":
                        return
                    while curr_task and curr_task["status"] == "paused":
                        await asyncio.sleep(_POLL_INTERVAL)
                        curr_task = await db.get_broadcast_task(task_id)
                        if not curr_task or curr_task["status"] == "stopped":
                            return

                    try:
                        await tm.ensure_membership(
                            account["session_string"],
                            account["phone"],
                            group["group_id"],
                            group.get("username"),
                        )
                        # Telegram spam filtriga tushmaslik uchun matnni har xil qilish
                        unique_text = apply_anti_flood_variation(message_text)
                        await tm.send_message_to_group(
                            account["session_string"],
                            account["phone"],
                            group["group_id"],
                            unique_text,
                            group.get("username"),
                        )
                        logger.info(
                            f"[{task_id}] {account['phone']} -> {group['title']}: yuborildi"
                        )
                        # Tabiiy, insoniy oraliq (3 dan 6 soniyagacha tasodifiy kutish)
                        delay = random.uniform(3.0, 6.0)
                        await asyncio.sleep(delay)
                    except asyncio.CancelledError:
                        raise
                    except Exception as e:
                        if isinstance(e, errors.FloodWaitError):
                            wait_sec = getattr(e, "seconds", 30)
                            logger.warning(
                                f"[{task_id}] FloodWait {wait_sec}s ({account['phone']})"
                            )
                            if wait_sec <= 60:
                                await asyncio.sleep(wait_sec + 2)
                        err_reason = _format_send_error(e)
                        logger.error(
                            f"[{task_id}] Xatolik {account['phone']} -> {group['title']}: {e}"
                        )
                        un_str = f" (@{group['username']})" if group.get("username") else ""
                        phone = account['phone']
                        clean_phone = phone.replace(" ", "").replace("-", "")
                        if not clean_phone.startswith("+"):
                            clean_phone = f"+{clean_phone}"
                        phone_link = f'<a href="https://t.me/{clean_phone}">{phone}</a>'
                        title_escaped = html.escape(str(group.get('title') or ''))
                        reason_escaped = html.escape(str(err_reason))
                        notify_msg = (
                            f"⚠️ <b>Guruhga xabar yuborilmadi!</b>\n\n"
                            f"📢 <b>Tarqatish:</b> #{task_id}\n"
                            f"👤 <b>Akkaunt:</b> {phone_link}\n"
                            f"🏘 <b>Guruh:</b> <b>{title_escaped}</b>{un_str}\n"
                            f"❌ <b>Sabab:</b> <i>{reason_escaped}</i>"
                        )
                        await self._notify_admins(notify_msg)

                        err_lower = str(e).lower()
                        if (
                            "authorization has been invalidated" in err_lower
                            or "deauthorized" in err_lower
                            or "session_revoked" in err_lower
                            or "session_expired" in err_lower
                            or "sessionpasswordneeded" in err_lower
                        ):
                            logger.warning(
                                f"[{task_id}] Akkaunt {account['phone']} sessiyasi bekor qilingan, nofaol holatga o'tkazildi."
                            )
                            await db.update_account_status(account["id"], 0)
                            await tm.disconnect_and_remove(account["phone"])
                            break

                finish_time = asyncio.get_event_loop().time()
                last_sent[account["id"]] = finish_time
                finish_wall = datetime.now()
                try:
                    await db.record_account_last_sent(task_id, account["id"], finish_wall.isoformat())
                except Exception as ex:
                    logger.warning(f"[{task_id}] record_account_last_sent xatosi: {ex}")

                # Next run for this account:
                # 1. At least cycle_sec (e.g. 6 min) from its own finish time
                # 2. Spaced at least stagger_sec after the last scheduled account in the queue
                other_times = [t for a_id, t in schedule.items() if a_id != account["id"]]
                if other_times:
                    min_after_others = max(other_times) + stagger_sec
                    schedule[account["id"]] = max(finish_time + cycle_sec, min_after_others)
                else:
                    schedule[account["id"]] = finish_time + cycle_sec

                try:
                    await tm.disconnect_client(account["phone"])
                except Exception as _e:
                    logger.warning(f"[{task_id}] disconnect xatosi {account['phone']}: {_e}")

                next_wall = self._mono_to_wall(schedule[account["id"]]).strftime("%H:%M:%S")
                logger.info(
                    f"[{task_id}] {account['phone']} barcha guruhlarga yubordi. "
                    f"Keyingi navbati {task_data.get('interval_minutes', 6)} daqiqadan so'ng ({next_wall}) bo'ladi."
                )

                await asyncio.sleep(0.5)

        except asyncio.CancelledError:
            logger.info(f"Broadcast {task_id} bekor qilindi")
            raise
        except Exception as e:
            logger.error(f"Broadcast {task_id} kutilmagan xato: {e}")
            await db.update_broadcast_status(task_id, "stopped")