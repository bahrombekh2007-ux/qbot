"""Subscription va rate limiting xizmati - Redis-siz, SQLite bilan."""
from datetime import datetime, timedelta
from typing import Tuple
import logging

from bot.db.session import get_session
from bot.db.models import User, DailyUsage, SubscriptionTier
from bot.config import settings
from sqlalchemy import select, and_

logger = logging.getLogger(__name__)


# Tariflar konfiguratsiyasi
TIER_LIMITS = {
    SubscriptionTier.FREE: {
        "tests_per_day": settings.free_tests_per_day,
        "tests_per_month": settings.free_tests_per_month,
        "max_questions": settings.max_free_questions,
        "max_file_size_mb": 10,
        "features": ["basic_quiz", "telegram_share"],
    },
    SubscriptionTier.PRO: {
        "tests_per_day": 50,
        "tests_per_month": 1000,
        "max_questions": 30,
        "max_file_size_mb": 20,
        "features": ["basic_quiz", "telegram_share", "pdf_export", "analytics"],
    },
    SubscriptionTier.PREMIUM: {
        "tests_per_day": 500,
        "tests_per_month": 10000,
        "max_questions": 50,
        "max_file_size_mb": 50,
        "features": [
            "basic_quiz", "telegram_share", "pdf_export", "analytics",
            "ai_explanations", "image_questions", "share_marketplace",
        ],
    },
    SubscriptionTier.LIFETIME: {
        "tests_per_day": 99999,
        "tests_per_month": 99999,
        "max_questions": 100,
        "max_file_size_mb": 100,
        "features": ["all"],
    },
}


class SubscriptionService:
    """Tarif va limitlarni boshqarish."""

    @staticmethod
    def get_tier_limits(tier: SubscriptionTier) -> dict:
        return TIER_LIMITS.get(tier, TIER_LIMITS[SubscriptionTier.FREE])

    async def get_user_tier(self, telegram_id: int) -> Tuple[SubscriptionTier, dict]:
        """Foydalanuvchi tarifini va limitlarini olish."""
        async with get_session() as session:
            stmt = select(User).where(User.telegram_id == telegram_id)
            user = (await session.execute(stmt)).scalar_one_or_none()

            if not user:
                return SubscriptionTier.FREE, TIER_LIMITS[SubscriptionTier.FREE]

            tier = user.subscription_tier
            # Muddati tugaganmi?
            if user.subscription_expires and user.subscription_expires < datetime.utcnow():
                if tier != SubscriptionTier.FREE:
                    user.subscription_tier = SubscriptionTier.FREE
                    await session.commit()
                tier = SubscriptionTier.FREE

            return tier, TIER_LIMITS[tier]

    async def check_quota(
        self,
        telegram_id: int,
        user_id: int,
    ) -> Tuple[bool, str, dict]:
        """Foydalanuvchi limit tekshiruvi."""
        tier, limits = await self.get_user_tier(telegram_id)

        async with get_session() as session:
            today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
            stmt = select(DailyUsage).where(
                and_(
                    DailyUsage.user_id == user_id,
                    DailyUsage.date >= today,
                )
            )
            usage = (await session.execute(stmt)).scalar_one_or_none()
            tests_today = usage.tests_count if usage else 0

            stats = {
                "tier": tier.value,
                "tests_today": tests_today,
                "tests_per_day_limit": limits["tests_per_day"],
                "remaining": max(0, limits["tests_per_day"] - tests_today),
            }

            if tests_today >= limits["tests_per_day"]:
                return False, (
                    f"❌ Kunlik limit tugadi ({limits['tests_per_day']} ta test).\n\n"
                    f"💎 Premium olib, limitsiz foydalaning!"
                ), stats

            return True, "ok", stats

    async def increment_usage(self, user_id: int, questions: int = 0) -> None:
        """Foydalanishni +1 ga oshirish."""
        async with get_session() as session:
            today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
            stmt = select(DailyUsage).where(
                and_(
                    DailyUsage.user_id == user_id,
                    DailyUsage.date >= today,
                )
            )
            usage = (await session.execute(stmt)).scalar_one_or_none()

            if usage:
                usage.tests_count += 1
                usage.questions_count += questions
            else:
                usage = DailyUsage(
                    user_id=user_id,
                    date=today,
                    tests_count=1,
                    questions_count=questions,
                )
                session.add(usage)

    async def upgrade_tier(
        self,
        user_id: int,
        new_tier: SubscriptionTier,
        duration_days: int = 30,
    ) -> None:
        """Tarifni yangilash."""
        async with get_session() as session:
            stmt = select(User).where(User.id == user_id)
            user = (await session.execute(stmt)).scalar_one_or_none()
            if not user:
                return

            user.subscription_tier = new_tier
            if new_tier == SubscriptionTier.LIFETIME:
                user.subscription_expires = None
            else:
                base = user.subscription_expires or datetime.utcnow()
                if base < datetime.utcnow():
                    base = datetime.utcnow()
                user.subscription_expires = base + timedelta(days=duration_days)

    async def start_trial(self, user_id: int) -> bool:
        """3 kunlik trial boshlash (faqat 1 marta)."""
        async with get_session() as session:
            stmt = select(User).where(User.id == user_id)
            user = (await session.execute(stmt)).scalar_one_or_none()

            if not user or user.trial_used:
                return False

            user.subscription_tier = SubscriptionTier.PREMIUM
            user.subscription_expires = datetime.utcnow() + timedelta(days=settings.trial_days)
            user.trial_used = True
            return True


subscription_service = SubscriptionService()
