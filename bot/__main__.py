"""Bot entry point - Render.com uchun optimized.

Bitta jarayon ichida:
  - Telegram bot (polling rejimi)
  - REST API server (aiohttp)
  - WebApp static fayllar

Bu Render free tier uchun ideal — faqat 1 ta service.
"""
import asyncio
import logging
import sys
import os
from pathlib import Path

# Loyiha ildiziga yo'l qo'shish
sys.path.insert(0, str(Path(__file__).parent.parent))

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiohttp import web

from bot.config import settings
from bot.db.session import init_db
from bot.handlers import setup_routers
from bot.middlewares import (
    ThrottlingMiddleware, UserActivityMiddleware, ErrorMiddleware
)

# Logging
os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("logs/bot.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)


async def create_api_app() -> web.Application:
    """API va static fayllar uchun aiohttp app."""
    from api.server import create_app
    return create_app()


async def run_bot(bot: Bot, dp: Dispatcher):
    """Bot polling."""
    logger.info("Bot polling boshlandi...")
    await dp.start_polling(
        bot,
        allowed_updates=["message", "callback_query", "inline_query", "pre_checkout_query"],
    )


async def run_api(app: web.Application, host: str, port: int):
    """API server."""
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    logger.info(f"API server {host}:{port} da ishlamoqda")
    # Cheksiz kutish
    while True:
        await asyncio.sleep(3600)


async def main():
    """Asosiy entry point - bot + API birgalikda."""

    # Bot
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    # Dispatcher - MemoryStorage (Render free tier uchun yetarli)
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)

    # Middlewares
    dp.message.middleware(ErrorMiddleware())
    dp.callback_query.middleware(ErrorMiddleware())
    dp.message.middleware(ThrottlingMiddleware())
    dp.callback_query.middleware(ThrottlingMiddleware())
    dp.message.middleware(UserActivityMiddleware())
    dp.callback_query.middleware(UserActivityMiddleware())

    # Routers
    main_router = setup_routers()
    dp.include_router(main_router)

    # DB yaratish
    logger.info("Database yaratilmoqda...")
    await init_db()

    # Bot ma'lumotlari
    bot_info = await bot.get_me()
    logger.info(f"Bot @{bot_info.username} ({bot_info.id}) ishga tushdi")

    # Webhook o'chirish (polling rejimi)
    await bot.delete_webhook(drop_pending_updates=True)

    # API app
    api_app = await create_api_app()

    # PORT - Render avtomatik beradi
    port = int(os.getenv("PORT", settings.api_port))

    # Birgalikda ishga tushurish
    logger.info(f"Barcha xizmatlar ishga tushmoqda (PORT={port})...")

    await asyncio.gather(
        run_bot(bot, dp),
        run_api(api_app, settings.api_host, port),
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot to'xtatildi")
    except Exception as e:
        logger.exception(f"Fatal error: {e}")
        sys.exit(1)
