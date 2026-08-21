import json
import os
import aiosqlite


def get_db_path() -> str:
    return os.getenv("DB_PATH", "bot.db")


async def init_db():
    async with aiosqlite.connect(get_db_path()) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                phone TEXT NOT NULL UNIQUE,
                session_string TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS groups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_id INTEGER NOT NULL UNIQUE,
                title TEXT NOT NULL,
                username TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS broadcast_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_text TEXT NOT NULL,
                account_ids TEXT NOT NULL,
                group_ids TEXT NOT NULL,
                interval_seconds INTEGER NOT NULL DEFAULT 30,
                interval_minutes INTEGER DEFAULT 1,
                stagger_seconds INTEGER NOT NULL DEFAULT 60,
                status TEXT NOT NULL DEFAULT 'stopped',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        try:
            await db.execute(
                "ALTER TABLE broadcast_tasks ADD COLUMN interval_seconds INTEGER NOT NULL DEFAULT 30"
            )
        except Exception:
            pass
        try:
            await db.execute(
                "ALTER TABLE broadcast_tasks ADD COLUMN stagger_seconds INTEGER NOT NULL DEFAULT 60"
            )
        except Exception:
            pass
        await db.commit()


async def reset_running_tasks():
    async with aiosqlite.connect(get_db_path()) as db:
        await db.execute(
            "UPDATE broadcast_tasks SET status = 'stopped' WHERE status IN ('running', 'paused')"
        )
        await db.commit()


async def get_all_accounts() -> list:
    async with aiosqlite.connect(get_db_path()) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM accounts ORDER BY created_at") as cur:
            return [dict(r) for r in await cur.fetchall()]


async def get_active_accounts() -> list:
    async with aiosqlite.connect(get_db_path()) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM accounts WHERE is_active = 1 ORDER BY created_at"
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def get_account_by_id(account_id: int) -> dict | None:
    async with aiosqlite.connect(get_db_path()) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def get_account_by_phone(phone: str) -> dict | None:
    async with aiosqlite.connect(get_db_path()) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM accounts WHERE phone = ?", (phone,)) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def add_account(phone: str, session_string: str):
    async with aiosqlite.connect(get_db_path()) as db:
        await db.execute(
            "INSERT INTO accounts (phone, session_string, is_active) VALUES (?, ?, 1)",
            (phone, session_string),
        )
        await db.commit()


async def delete_account(account_id: int):
    async with aiosqlite.connect(get_db_path()) as db:
        await db.execute("DELETE FROM accounts WHERE id = ?", (account_id,))
        await db.commit()


async def get_all_groups() -> list:
    async with aiosqlite.connect(get_db_path()) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM groups ORDER BY title") as cur:
            return [dict(r) for r in await cur.fetchall()]


async def save_groups(groups: list):
    async with aiosqlite.connect(get_db_path()) as db:
        for g in groups:
            await db.execute(
                "INSERT OR REPLACE INTO groups (group_id, title, username) VALUES (?, ?, ?)",
                (g["group_id"], g["title"], g.get("username")),
            )
        await db.commit()


async def get_group_by_id(group_id: int) -> dict | None:
    async with aiosqlite.connect(get_db_path()) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM groups WHERE id = ?", (group_id,)) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def delete_group(group_db_id: int):
    async with aiosqlite.connect(get_db_path()) as db:
        await db.execute("DELETE FROM groups WHERE id = ?", (group_db_id,))
        await db.commit()


async def delete_all_groups():
    async with aiosqlite.connect(get_db_path()) as db:
        await db.execute("DELETE FROM groups")
        await db.commit()


async def create_broadcast_task(
    message_text: str,
    account_ids: list,
    group_ids: list,
    interval_seconds: int = 30,
    interval_minutes: int = 1,
    stagger_seconds: int = 60,
) -> int:
    async with aiosqlite.connect(get_db_path()) as db:
        cur = await db.execute(
            "INSERT INTO broadcast_tasks "
            "(message_text, account_ids, group_ids, interval_seconds, interval_minutes, stagger_seconds, status) "
            "VALUES (?, ?, ?, ?, ?, ?, 'stopped')",
            (
                message_text,
                json.dumps(account_ids),
                json.dumps(group_ids),
                interval_seconds,
                interval_minutes,
                stagger_seconds,
            ),
        )
        await db.commit()
        return cur.lastrowid


async def get_broadcast_task(task_id: int) -> dict | None:
    async with aiosqlite.connect(get_db_path()) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM broadcast_tasks WHERE id = ?", (task_id,)
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def update_broadcast_status(task_id: int, status: str):
    async with aiosqlite.connect(get_db_path()) as db:
        await db.execute(
            "UPDATE broadcast_tasks SET status = ? WHERE id = ?", (status, task_id)
        )
        await db.commit()


async def delete_broadcast_task(task_id: int):
    async with aiosqlite.connect(get_db_path()) as db:
        await db.execute("DELETE FROM broadcast_tasks WHERE id = ?", (task_id,))
        await db.commit()


async def get_all_broadcast_tasks() -> list:
    async with aiosqlite.connect(get_db_path()) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM broadcast_tasks ORDER BY created_at DESC"
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]