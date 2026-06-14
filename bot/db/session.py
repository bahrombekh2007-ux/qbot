"""Database engine va session - SQLite async."""
from sqlalchemy.ext.asyncio import (
    create_async_engine, AsyncSession, async_sessionmaker
)
from contextlib import asynccontextmanager
from bot.config import settings
from bot.db.models import Base
import os

# Data papkasini yaratish
os.makedirs("data", exist_ok=True)

# Engine - SQLite uchun pool sozlamalari boshqacha
engine = create_async_engine(
    settings.database_url,
    echo=False,
    # SQLite uchun connect_args
    connect_args={"check_same_thread": False} if "sqlite" in settings.database_url else {},
)

# Session factory
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def init_db():
    """Bazani yaratish."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@asynccontextmanager
async def get_session() -> AsyncSession:
    """Session context manager."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def get_db():
    """Dependency uchun generator."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
