import asyncio
import logging
import os

from dotenv import load_dotenv

load_dotenv()

from aiogram import Bot, Dispatcher, Router
from aiogram.types import Message, CallbackQuery
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from database.db import init_db, reset_running_tasks
from handlers import accounts, broadcast, groups, menu
from keyboards.inline import main_menu_keyboard
from services.broadcaster import BroadcastManager


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    handlers=[
        logging.FileHandler("bot.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)

logger = logging.getLogger(__name__)


async def main():
    await init_db()
    await reset_running_tasks()

    bot = Bot(
        token=os.getenv("BOT_TOKEN"),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())

    broadcast_manager = BroadcastManager()
    dp["broadcast_manager"] = broadcast_manager

    dp.include_router(menu.router)
    dp.include_router(accounts.router)
    dp.include_router(groups.router)
    dp.include_router(broadcast.router)

    fallback_router = Router()

    @fallback_router.message()
    async def fallback_message(message: Message):
        raw = os.getenv("ADMIN_IDS", "")
        admin_ids = [int(x.strip()) for x in raw.split(",") if x.strip().isdigit()]
        is_admin = message.from_user.id in admin_ids if message.from_user else False

        if is_admin:
            await message.answer(
                "🤖 <b>Boshqaruv paneli</b>\n\nBo'limni tanlang:",
                reply_markup=main_menu_keyboard(),
                parse_mode="HTML"
            )
        else:
            logger.info(f"Non-admin access attempt from Telegram ID: {message.from_user.id}")
            await message.answer(
                f"⛔ <b>Siz admin emassiz!</b>\n\n"
                f"Sizning Telegram ID: <code>{message.from_user.id}</code>\n\n"
                f"Boshqaruv panelidan foydalanish uchun ushbu ID ni <code>.env</code> faylidagi <code>ADMIN_IDS</code> qatoriga qo'shing.",
                parse_mode="HTML"
            )

    @fallback_router.callback_query()
    async def fallback_callback(callback: CallbackQuery):
        raw = os.getenv("ADMIN_IDS", "")
        admin_ids = [int(x.strip()) for x in raw.split(",") if x.strip().isdigit()]
        is_admin = callback.from_user.id in admin_ids if callback.from_user else False

        if is_admin:
            await callback.answer()
        else:
            await callback.answer(
                f"⛔ Siz admin emassiz! (ID: {callback.from_user.id})",
                show_alert=True
            )

    dp.include_router(fallback_router)

    logger.info("Bot ishga tushdi")
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
