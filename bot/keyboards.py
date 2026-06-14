"""Bot uchun klaviaturalar (inline va reply)."""
from aiogram.types import (
    InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, KeyboardButton, WebAppInfo
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from bot.config import settings


def get_main_reply_keyboard(lang: str = "uz") -> ReplyKeyboardMarkup:
    """Asosiy reply klaviatura - WebApp tugmasi bilan."""
    texts = {
        "uz": {
            "create": "📝 Test yaratish",
            "my": "📚 Mening testlarim",
            "stats": "📊 Statistika",
            "premium": "💎 Premium",
            "help": "ℹ️ Yordam",
        },
        "ru": {
            "create": "📝 Создать тест",
            "my": "📚 Мои тесты",
            "stats": "📊 Статистика",
            "premium": "💎 Премиум",
            "help": "ℹ️ Помощь",
        },
        "en": {
            "create": "📝 Create quiz",
            "my": "📚 My quizzes",
            "stats": "📊 Statistics",
            "premium": "💎 Premium",
            "help": "ℹ️ Help",
        },
    }
    t = texts.get(lang, texts["uz"])

    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(
                    text=t["create"],
                    web_app=WebAppInfo(url=f"{settings.webapp_url}?action=create"),
                )
            ],
            [
                KeyboardButton(
                    text=t["my"],
                    web_app=WebAppInfo(url=f"{settings.webapp_url}?action=my"),
                ),
                KeyboardButton(
                    text=t["stats"],
                    web_app=WebAppInfo(url=f"{settings.webapp_url}?action=stats"),
                ),
            ],
            [
                KeyboardButton(
                    text=t["premium"],
                    web_app=WebAppInfo(url=f"{settings.webapp_url}?action=premium"),
                ),
                KeyboardButton(text=t["help"]),
            ],
        ],
        resize_keyboard=True,
        input_field_placeholder="Quyidagilardan birini tanlang...",
    )
    return keyboard


def get_start_keyboard() -> InlineKeyboardMarkup:
    """Start komandasi uchun inline klaviatura."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="🚀 WebApp ochish",
            web_app=WebAppInfo(url=settings.webapp_url),
        )
    )
    builder.row(
        InlineKeyboardButton(text="📖 Qo'llanma", callback_data="help"),
        InlineKeyboardButton(text="💎 Premium", callback_data="premium"),
    )
    builder.row(
        InlineKeyboardButton(
            text="➕ Guruhga qo'shish",
            url=f"https://t.me/{settings.bot_username}?startgroup=true",
        )
    )
    return builder.as_markup()


def get_premium_keyboard() -> InlineKeyboardMarkup:
    """Premium tariflari."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="🥉 PRO - 49 900 so'm/oy",
            callback_data="buy_pro_monthly",
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="🥈 PREMIUM - 499 000 so'm/yil",
            callback_data="buy_premium_yearly",
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="👑 LIFETIME - 999 000 so'm",
            callback_data="buy_lifetime",
        )
    )
    builder.row(
        InlineKeyboardButton(text="🎁 Bepul sinash (3 kun)", callback_data="start_trial")
    )
    builder.row(
        InlineKeyboardButton(text="🔙 Orqaga", callback_data="back_to_main")
    )
    return builder.as_markup()


def get_language_keyboard() -> InlineKeyboardMarkup:
    """Til tanlash."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🇺🇿 O'zbek", callback_data="lang_uz"),
        InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang_ru"),
    )
    builder.row(
        InlineKeyboardButton(text="🇬🇧 English", callback_data="lang_en"),
    )
    return builder.as_markup()


def get_quiz_settings_keyboard() -> InlineKeyboardMarkup:
    """Test yaratish jarayonida sozlamalar."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="5 ta savol", callback_data="count_5"),
        InlineKeyboardButton(text="10 ta savol", callback_data="count_10"),
    )
    builder.row(
        InlineKeyboardButton(text="20 ta savol", callback_data="count_20"),
        InlineKeyboardButton(text="50 ta savol", callback_data="count_50"),
    )
    builder.row(
        InlineKeyboardButton(text="🎯 Oson", callback_data="diff_easy"),
        InlineKeyboardButton(text="⚖️ O'rta", callback_data="diff_medium"),
    )
    builder.row(
        InlineKeyboardButton(text="🔥 Qiyin", callback_data="diff_hard"),
        InlineKeyboardButton(text="🎲 Aralash", callback_data="diff_mixed"),
    )
    builder.row(
        InlineKeyboardButton(text="✅ Tayyor", callback_data="generate_quiz"),
        InlineKeyboardButton(text="❌ Bekor", callback_data="cancel"),
    )
    return builder.as_markup()


def get_payment_method_keyboard(plan: str) -> InlineKeyboardMarkup:
    """To'lov usulini tanlash."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="⭐ Telegram Stars",
            callback_data=f"pay_stars_{plan}",
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="💳 Payme",
            callback_data=f"pay_payme_{plan}",
        ),
        InlineKeyboardButton(
            text="💳 Click",
            callback_data=f"pay_click_{plan}",
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="🔙 Orqaga",
            callback_data="premium",
        )
    )
    return builder.as_markup()


def get_share_keyboard(test_id: int) -> InlineKeyboardMarkup:
    """Test natijasini ulashish."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="📤 Do'stlar bilan ulashish",
            switch_inline_query=f"test_{test_id}",
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="🏆 Reytingda ko'rish",
            callback_data=f"leaderboard_{test_id}",
        ),
        InlineKeyboardButton(
            text="🔁 Qayta yechish",
            callback_data=f"retake_{test_id}",
        ),
    )
    return builder.as_markup()
