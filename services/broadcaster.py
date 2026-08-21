import asyncio
import json
import logging
import time
from datetime import datetime
from database import db
from services import telethon_manager as tm

logger = logging.getLogger(__name__)

_POLL_INTERVAL = 5.0


def _format_send_error(e: Exception) -> str:
    err_str = str(e)
    err_lower = err_str.lower()
    if "chatwriteforbidden" in err_lower or "cannot write" in err_lower or "write forbidden" in err_lower:
        return "Guruhda a'zolarga xabar yozish ruxsati yo'q (yopilgan)"
    if "userbannedinchannel" in err_lower or "banned" in err_lower or "restricted" in err_lower:
        return "Akkaunt bu guruhda bloklangan (ban qilingan)"
    if "slowmodewait" in err_lower:
        return f"Guruhda sekin rejim (Slowmode) yoqilgan"
    if "floodwait" in err_lower:
        return f"Telegram cheklovi (FloodWait: biroz kutish kerak)"
    if "session" in err_lower or "deauthorized" in err_lower or "invalidated" in err_lower:
        return "Akkaunt sessiyasi bekor qilingan (chiqib ketilgan)"
    if "channelprivate" in err_lower or "chatidinvalid" in err_lower or "could not find" in err_lower:
        return "Guruh topilmadi yoki unga kirish imkoni yo'q"
    return err_str


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

    def get_account_stats(self, task_id: int, accounts: list[dict]) -> list[dict]:
        schedule = self._next_send_time.get(task_id, {})
        last_sent = self._last_sent_time.get(task_id, {})
        now_mono = asyncio.get_event_loop().time()
        result = []
        for acc in accounts:
            acc_id = acc["id"]
            next_mono = schedule.get(acc_id)
            last_mono = last_sent.get(acc_id)

            if next_mono is not None:
                remaining_sec = max(0.0, next_mono - now_mono)
                next_dt = self._mono_to_wall(next_mono)
            else:
                remaining_sec = None
                next_dt = None

            last_dt = self._mono_to_wall(last_mono) if last_mono is not None else None

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
        self._last_sent_time.pop(task_id, None)
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
        self._last_sent_time.pop(task_id, None)
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
                        await tm.send_message_to_group(
                            account["session_string"],
                            account["phone"],
                            group["group_id"],
                            message_text,
                            group.get("username"),
                        )
                        logger.info(
                            f"[{task_id}] {account['phone']} -> {group['title']}: yuborildi"
                        )
                        await asyncio.sleep(1)
                    except asyncio.CancelledError:
                        raise
                    except Exception as e:
                        err_reason = _format_send_error(e)
                        logger.error(
                            f"[{task_id}] Xatolik {account['phone']} -> {group['title']}: {e}"
                        )
                        un_str = f" (@{group['username']})" if group.get("username") else ""
                        notify_msg = (
                            f"⚠️ <b>Guruhga xabar yuborilmadi!</b>\n\n"
                            f"📢 <b>Tarqatish:</b> #{task_id}\n"
                            f"👤 <b>Akkaunt:</b> <code>{account['phone']}</code>\n"
                            f"🏘 <b>Guruh:</b> <b>{group['title']}</b>{un_str}\n"
                            f"❌ <b>Sabab:</b> <i>{err_reason}</i>"
                        )
                        await self._notify_admins(notify_msg)

                finish_time = asyncio.get_event_loop().time()
                last_sent[account["id"]] = finish_time

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