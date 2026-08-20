import asyncio
import json
import logging
import time
from datetime import datetime
from database import db
from services import telethon_manager as tm

logger = logging.getLogger(__name__)

_POLL_INTERVAL = 5.0


class BroadcastManager:
    def __init__(self):
        self._tasks: dict[int, asyncio.Task] = {}
        self._next_send_time: dict[int, dict[int, float]] = {}
        self._last_sent_time: dict[int, dict[int, float]] = {}

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
                interval_sec = task_data["interval_minutes"] * 60
                stagger_sec = task_data.get("stagger_seconds", 60)
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

                now = asyncio.get_event_loop().time()

                for idx, acc in enumerate(accounts):
                    if acc["id"] not in schedule:
                        schedule[acc["id"]] = now + idx * stagger_sec

                due_accounts = [
                    acc for acc in accounts
                    if schedule.get(acc["id"], 0) <= asyncio.get_event_loop().time()
                ]

                if not due_accounts:
                    earliest = min(schedule[acc["id"]] for acc in accounts)
                    wait = min(max(earliest - asyncio.get_event_loop().time(), 0.1), _POLL_INTERVAL)
                    await asyncio.sleep(wait)
                    continue

                for account in due_accounts:
                    status_check = await db.get_broadcast_task(task_id)
                    if not status_check or status_check["status"] == "stopped":
                        return

                    while status_check and status_check["status"] == "paused":
                        await asyncio.sleep(_POLL_INTERVAL)
                        status_check = await db.get_broadcast_task(task_id)
                        if not status_check or status_check["status"] == "stopped":
                            return

                    for group in groups:
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
                            await asyncio.sleep(3)
                        except asyncio.CancelledError:
                            raise
                        except Exception as e:
                            logger.error(
                                f"[{task_id}] Xatolik {account['phone']} -> {group['title']}: {e}"
                            )

                    last_sent[account["id"]] = asyncio.get_event_loop().time()
                    next_time = asyncio.get_event_loop().time() + interval_sec
                    schedule[account["id"]] = next_time
                    try:
                        await tm.disconnect_client(account["phone"])
                    except Exception as _e:
                        logger.warning(f"[{task_id}] disconnect xatosi {account['phone']}: {_e}")
                    logger.info(
                        f"[{task_id}] {account['phone']} tarqatdi, disconnect qilindi. "
                        f"Keyingisi {task_data['interval_minutes']} daqiqadan keyin."
                    )

                await asyncio.sleep(1)

        except asyncio.CancelledError:
            logger.info(f"Broadcast {task_id} bekor qilindi")
            raise
        except Exception as e:
            logger.error(f"Broadcast {task_id} kutilmagan xato: {e}")
            await db.update_broadcast_status(task_id, "stopped")