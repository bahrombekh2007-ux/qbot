"""Bot uchun middlewares - logging, throttling, auth."""
import time
import logging
from typing import Any, Awaitable, Callable, Dict
from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery, TelegramObject
from aiogram.exceptions import TelegramAPIError
from cachetools import TTLCache

logger = logging.getLogger(__name__)


class ThrottlingMiddleware(BaseMiddleware):
    """Foydalanuvchini throttle qilish - spam ga qarshi.

    1 soniyada 1 ta xabar, 5 soniyada 10 ta xabar limiti.
    """

    def __init__(self, rate_limit: float = 1.0, burst_limit: int = 10):
        self.rate_limit = rate_limit
        self.burst_limit = burst_limit
        # Cache: user_id -> [last_message_time, burst_count, window_start]
        self.cache: Dict[int, list] = TTLCache(maxsize=10_000, ttl=60)

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        if not user:
            return await handler(event, data)

        user_id = user.id
        current_time = time.time()

        if user_id in self.cache:
            times = self.cache[user_id]
            # Eski yozuvlarni tozalash
            times = [t for t in times if current_time - t < 5.0]
        else:
            times = []

        # Burst limit
        if len(times) >= self.burst_limit:
            logger.warning(f"Throttled user {user_id} (burst)")
            if isinstance(event, Message):
                await event.answer("⏳ Sekinroq yozing, iltimos...")
            elif isinstance(event, CallbackQuery):
                await event.answer("⏳ Sekinroq", show_alert=False)
            return None

        # Rate limit
        if times and current_time - times[-1] < self.rate_limit:
            if isinstance(event, Message):
                return None  # Sukut
            elif isinstance(event, CallbackQuery):
                await event.answer("⏳")
                return None

        times.append(current_time)
        self.cache[user_id] = times

        return await handler(event, data)


class UserActivityMiddleware(BaseMiddleware):
    """Foydalanuvchi faolligini kuzatish va ro'yxatga olish."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        if not user:
            return await handler(event, data)

        # Foydalanuvchini ro'yxatga olish yoki yangilash
        from bot.db.session import get_session
        from bot.db.models import User
        from datetime import datetime
        from sqlalchemy import select

        async with get_session() as session:
            stmt = select(User).where(User.telegram_id == user.id)
            db_user = (await session.execute(stmt)).scalar_one_or_none()

            if not db_user:
                db_user = User(
                    telegram_id=user.id,
                    username=user.username,
                    first_name=user.first_name or "User",
                    last_name=user.last_name,
                    language_code=user.language_code or "uz",
                    last_active=datetime.utcnow(),
                )
                session.add(db_user)
                logger.info(f"New user registered: {user.id}")
            else:
                db_user.last_active = datetime.utcnow()
                # Ma'lumotlarni yangilash
                if user.username and db_user.username != user.username:
                    db_user.username = user.username
                if user.first_name and db_user.first_name != user.first_name:
                    db_user.first_name = user.first_name
                if user.last_name and db_user.last_name != user.last_name:
                    db_user.last_name = user.last_name

        data["db_user"] = db_user
        return await handler(event, data)


class ErrorMiddleware(BaseMiddleware):
    """Xatolarni ushlash va foydalanuvchiga tushunarli xabar berish."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        try:
            return await handler(event, data)
        except TelegramAPIError as e:
            logger.error(f"Telegram API error: {e}", exc_info=True)
            try:
                if isinstance(event, Message):
                    await event.answer("⚠️ Telegramda texnik xato. Iltimos qaytadan urinib ko'ring.")
                elif isinstance(event, CallbackQuery):
                    await event.answer("⚠️ Texnik xato", show_alert=True)
            except Exception:
                pass
        except Exception as e:
            logger.exception(f"Unhandled error: {e}")
            try:
                if isinstance(event, Message):
                    await event.answer(
                        "❌ Kutilmagan xato yuz berdi. "
                        "Texnik mutaxassislar xabardor qilindi.\n\n"
                        "/start ni bosing va qaytadan urinib ko'ring."
                    )
            except Exception:
                pass
            # Sentry ga yuborish
            try:
                if settings.sentry_dsn:
                    import sentry_sdk
                    sentry_sdk.capture_exception(e)
            except Exception:
                pass
