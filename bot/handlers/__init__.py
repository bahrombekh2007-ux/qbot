"""Handlers paketi - barcha bot handlerlari."""
from aiogram import Router

from bot.handlers import main, files, payments


def setup_routers() -> Router:
    """Barcha routerlarni birlashtirish."""
    router = Router()
    router.include_router(main.router)
    router.include_router(files.router)
    router.include_router(payments.router)
    return router
