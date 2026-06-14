"""SQLAlchemy async modellari."""
from datetime import datetime
from typing import Optional, List
from sqlalchemy import (
    BigInteger, String, Text, Integer, Float, Boolean,
    DateTime, ForeignKey, JSON, Enum as SQLEnum, Index
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.ext.asyncio import AsyncAttrs
import enum


class Base(AsyncAttrs, DeclarativeBase):
    pass


class SubscriptionTier(enum.Enum):
    FREE = "free"
    PRO = "pro"
    PREMIUM = "premium"
    LIFETIME = "lifetime"


class TestStatus(enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class User(Base):
    """Foydalanuvchi modeli."""
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    first_name: Mapped[str] = mapped_column(String(128))
    last_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    language_code: Mapped[str] = mapped_column(String(8), default="uz")
    photo_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)

    # Subscription
    subscription_tier: Mapped[SubscriptionTier] = mapped_column(
        SQLEnum(SubscriptionTier), default=SubscriptionTier.FREE, index=True
    )
    subscription_expires: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    trial_used: Mapped[bool] = mapped_column(Boolean, default=False)

    # Statistika
    tests_created: Mapped[int] = mapped_column(Integer, default=0)
    tests_taken: Mapped[int] = mapped_column(Integer, default=0)
    total_score: Mapped[int] = mapped_column(Integer, default=0)
    streak_days: Mapped[int] = mapped_column(Integer, default=0)
    last_active: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Meta
    is_blocked: Mapped[bool] = mapped_column(Boolean, default=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    referrer_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relations
    tests: Mapped[List["Test"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    attempts: Mapped[List["TestAttempt"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Test(Base):
    """Test modeli."""
    __tablename__ = "tests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True)

    title: Mapped[str] = mapped_column(String(256))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_file: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    source_type: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)

    # Savollar JSON
    questions: Mapped[dict] = mapped_column(JSON, default=dict)

    # Sozlamalar
    total_questions: Mapped[int] = mapped_column(Integer, default=0)
    time_limit_seconds: Mapped[int] = mapped_column(Integer, default=0)
    passing_score: Mapped[int] = mapped_column(Integer, default=60)
    is_public: Mapped[bool] = mapped_column(Boolean, default=False)
    is_premium_only: Mapped[bool] = mapped_column(Boolean, default=False)

    # Status
    status: Mapped[TestStatus] = mapped_column(SQLEnum(TestStatus), default=TestStatus.PENDING, index=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Statistika
    times_taken: Mapped[int] = mapped_column(Integer, default=0)
    avg_score: Mapped[float] = mapped_column(Float, default=0.0)
    rating: Mapped[float] = mapped_column(Float, default=0.0)
    share_code: Mapped[Optional[str]] = mapped_column(String(16), unique=True, index=True, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    user: Mapped["User"] = relationship(back_populates="tests")
    attempts: Mapped[List["TestAttempt"]] = relationship(back_populates="test", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_tests_user_status", "user_id", "status"),
    )


class TestAttempt(Base):
    """Test yechish urinishlari."""
    __tablename__ = "test_attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    test_id: Mapped[int] = mapped_column(Integer, ForeignKey("tests.id", ondelete="CASCADE"), index=True)

    answers: Mapped[dict] = mapped_column(JSON, default=dict)

    correct_count: Mapped[int] = mapped_column(Integer, default=0)
    total_questions: Mapped[int] = mapped_column(Integer, default=0)
    score_percent: Mapped[float] = mapped_column(Float, default=0.0)
    passed: Mapped[bool] = mapped_column(Boolean, default=False)

    time_spent_seconds: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    user: Mapped["User"] = relationship(back_populates="attempts")
    test: Mapped["Test"] = relationship(back_populates="attempts")


class Payment(Base):
    """To'lovlar tarixi."""
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True)

    amount: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(8), default="UZS")
    provider: Mapped[str] = mapped_column(String(32))
    plan: Mapped[str] = mapped_column(String(32))

    external_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    payload: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class DailyUsage(Base):
    """Kundalik foydalanish statistikasi (rate limiting)."""
    __tablename__ = "daily_usage"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    date: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    tests_count: Mapped[int] = mapped_column(Integer, default=0)
    questions_count: Mapped[int] = mapped_column(Integer, default=0)

    __table_args__ = (
        Index("ix_daily_user_date", "user_id", "date", unique=True),
    )
