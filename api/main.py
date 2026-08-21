import asyncio
import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from dotenv import load_dotenv

# Asosiy loyiha katalogini sys.path ga qo'shish
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# .env yuklash
env_path = BASE_DIR / ".env"
load_dotenv(dotenv_path=env_path)

from fastapi import FastAPI, Request, Response, HTTPException, Header, status
import uvicorn
from aiogram import Bot, Dispatcher, Router
from aiogram.types import Message, CallbackQuery, Update
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
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
        logging.FileHandler(BASE_DIR / "bot.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)

logger = logging.getLogger(__name__)

# Webhook va Server sozlamalari
WEBHOOK_BASE_URL = os.getenv("WEBHOOK_BASE_URL", "").rstrip("/")
WEBHOOK_PATH = os.getenv("WEBHOOK_PATH", "/webhook")
if not WEBHOOK_PATH.startswith("/"):
    WEBHOOK_PATH = f"/{WEBHOOK_PATH}"

WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "").strip() or None
WEBAPP_HOST = os.getenv("WEBAPP_HOST", "0.0.0.0")
WEBAPP_PORT = int(os.getenv("WEBAPP_PORT", "8000"))
DROP_PENDING_UPDATES = os.getenv("DROP_PENDING_UPDATES", "true").lower() in ("true", "1", "yes")

# Bot va Dispatcher yaratish
session = AiohttpSession(timeout=60.0)
bot = Bot(
    token=os.getenv("BOT_TOKEN", ""),
    session=session,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)
dp = Dispatcher(storage=MemoryStorage())

# Xizmatlarni ulash
broadcast_manager = BroadcastManager(bot=bot)
dp["broadcast_manager"] = broadcast_manager

# Routerlarni ro'yxatdan o'tkazish
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
            parse_mode="HTML",
        )
    else:
        logger.info(f"Non-admin access attempt from Telegram ID: {message.from_user.id}")
        await message.answer(
            f"⛔ <b>Siz admin emassiz!</b>\n\n"
            f"Sizning Telegram ID: <code>{message.from_user.id}</code>\n\n"
            f"Boshqaruv panelidan foydalanish uchun ushbu ID ni <code>.env</code> faylidagi <code>ADMIN_IDS</code> qatoriga qo'shing.",
            parse_mode="HTML",
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
            show_alert=True,
        )


dp.include_router(fallback_router)


@dp.error()
async def global_error_handler(event):
    exc = event.exception
    from aiogram.exceptions import TelegramBadRequest, TelegramNetworkError

    if isinstance(exc, TelegramBadRequest) and "message is not modified" in str(exc).lower():
        if event.update and event.update.callback_query:
            try:
                await event.update.callback_query.answer()
            except Exception:
                pass
        return True

    if isinstance(exc, TelegramNetworkError):
        logger.warning(f"Telegram tarmoq xatosi / timeout: {exc}")
        return True

    logger.error(f"Kutilmagan xatolik: {exc}", exc_info=exc)
    return True


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Ma'lumotlar bazasi initsializatsiya qilinmoqda...")
    await init_db()
    await reset_running_tasks()

    if WEBHOOK_BASE_URL:
        full_webhook_url = f"{WEBHOOK_BASE_URL}{WEBHOOK_PATH}"
        logger.info(f"Webhook sozlanmoqda: {full_webhook_url}")
        await bot.set_webhook(
            url=full_webhook_url,
            secret_token=WEBHOOK_SECRET,
            drop_pending_updates=DROP_PENDING_UPDATES,
            allowed_updates=dp.resolve_used_update_types(),
        )
        logger.info("Webhook muvaffaqiyatli o'rnatildi.")
    else:
        logger.warning("DIQQAT: WEBHOOK_BASE_URL ko'rsatilmagan! Webhook avtomatik sozlanmadi.")

    yield

    # Shutdown
    logger.info("Bot to'xtatilmoqda...")
    try:
        await bot.session.close()
    except Exception as e:
        logger.error(f"Bot sessiyasini yopishda xatolik: {e}")


app = FastAPI(
    title="SuperTaxi2 Bot Webhook API",
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
)


@app.get("/")
async def root():
    return {
        "status": "ok",
        "service": "SuperTaxi2 Telegram Bot Webhook API",
    }


@app.get("/health")
async def health_check():
    return {"status": "healthy"}


@app.post(WEBHOOK_PATH)
async def bot_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(None, alias="X-Telegram-Bot-Api-Secret-Token"),
):
    if WEBHOOK_SECRET and x_telegram_bot_api_secret_token != WEBHOOK_SECRET:
        logger.warning("Maxfiy token (secret_token) mos kelmadi!")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid secret token",
        )

    try:
        data = await request.json()
        update = Update.model_validate(data, context={"bot": bot})
        await dp.feed_update(bot=bot, update=update)
    except Exception as e:
        logger.error(f"Update ni qayta ishlashda xatolik: {e}", exc_info=e)
        return Response(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)

    return Response(status_code=status.HTTP_200_OK)


if __name__ == "__main__":
    logger.info(f"FastAPI server ishga tushirilmoqda: {WEBAPP_HOST}:{WEBAPP_PORT}")
    uvicorn.run(app, host=WEBAPP_HOST, port=WEBAPP_PORT)
