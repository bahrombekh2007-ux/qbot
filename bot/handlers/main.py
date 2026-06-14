"""Asosiy bot handlerlari - start, yordam, WebApp boshqaruvi."""
import logging
from aiogram import Router, F
from aiogram.filters import Command, CommandStart, CommandObject
from aiogram.types import Message, CallbackQuery
from aiogram.enums import ParseMode
from aiogram.utils.markdown import hbold

from bot.config import settings
from bot.keyboards import (
    get_start_keyboard, get_premium_keyboard,
    get_language_keyboard, get_main_reply_keyboard
)
from bot.services.subscription import subscription_service

logger = logging.getLogger(__name__)
router = Router(name="main")


@router.message(CommandStart(deep_link=True))
async def cmd_start_with_ref(message: Message, command: CommandObject, db_user):
    """Start komandasi referral bilan."""
    args = command.args

    if args and args.startswith("test_"):
        test_id = args.replace("test_", "")
        await message.answer(
            f"🎯 Testga xush kelibsiz!\n\n"
            f"Test ID: {test_id}\n"
            f"Quyidagi tugma orqali oching:",
            reply_markup=get_start_keyboard(),
        )
        return

    if args and args.startswith("ref_"):
        try:
            referrer_id = int(args.replace("ref_", ""))
            if referrer_id != message.from_user.id:
                db_user.referrer_id = referrer_id
                # Bonus: 1 ta bepul test
                logger.info(f"User {message.from_user.id} referred by {referrer_id}")
        except ValueError:
            pass

    await cmd_start(message, db_user)


@router.message(CommandStart())
async def cmd_start(message: Message, db_user):
    """Asosiy start komandasi."""
    user = message.from_user
    name = user.first_name or "do'st"

    # Foydalanuvchi tilini aniqlash
    lang = db_user.language_code if db_user.language_code in ("uz", "ru", "en") else "uz"

    welcome_text = {
        "uz": (
            f"🎉 <b>Salom, {hbold(name)}!</b>\n\n"
            f"📚 <b>QuizMaster</b> - fayllaringizdan avtomatik test yaratuvchi bot.\n\n"
            f"📄 <b>Qo'llab-quvvatlanadigan formatlar:</b>\n"
            f"  • PDF, DOC, DOCX\n"
            f"  • XLSX, XLS\n"
            f"  • TXT, PPTX\n\n"
            f"⚡ <b>Qanday ishlaydi:</b>\n"
            f"1️⃣ Fayl yuklang\n"
            f"2️⃣ AI savollarni avtomatik yaratadi\n"
            f"3️⃣ Testni yeching va natijani ulashing\n\n"
            f"💎 Premium: 50 tagacha savol, katta fayllar, AI tushuntirishlar\n\n"
            f"Quyidagi tugmalardan birini tanlang 👇"
        ),
        "ru": (
            f"🎉 <b>Привет, {hbold(name)}!</b>\n\n"
            f"📚 <b>QuizMaster</b> - бот для создания тестов из ваших файлов.\n\n"
            f"📄 <b>Поддерживаемые форматы:</b>\n"
            f"  • PDF, DOC, DOCX\n"
            f"  • XLSX, XLS\n"
            f"  • TXT, PPTX\n\n"
            f"💎 Премиум: до 50 вопросов, большие файлы, AI-объяснения"
        ),
        "en": (
            f"🎉 <b>Hello, {hbold(name)}!</b>\n\n"
            f"📚 <b>QuizMaster</b> - bot that creates tests from your files.\n\n"
            f"📄 <b>Supported formats:</b>\n"
            f"  • PDF, DOC, DOCX\n"
            f"  • XLSX, XLS\n"
            f"  • TXT, PPTX"
        ),
    }

    await message.answer(
        welcome_text.get(lang, welcome_text["uz"]),
        parse_mode=ParseMode.HTML,
        reply_markup=get_main_reply_keyboard(lang),
    )

    # Agar yangi foydalanuvchi bo'lsa - taklif xabari
    if db_user.tests_created == 0:
        await message.answer(
            "💡 <b>Maslahat:</b> WebApp tugmasini bosing va birinchi testingizni yarating!",
            parse_mode=ParseMode.HTML,
        )


@router.message(Command("help"))
@router.message(F.text.in_({"ℹ️ Yordam", "ℹ️ Помощь", "ℹ️ Help"}))
async def cmd_help(message: Message):
    """Yordam komandasi."""
    text = (
        "📖 <b>Qo'llanma</b>\n\n"

        "🔹 <b>Test yaratish:</b>\n"
        "1. /start ni bosing yoki pastdagi tugmani\n"
        "2. WebApp ochiladi\n"
        "3. Fayl yuklang (PDF, DOCX, va h.k.)\n"
        "4. Sozlamalarni tanlang (savollar soni, qiyinlik)\n"
        "5. AI avtomatik savollar yaratadi\n"
        "6. Testni yeching yoki ulashing\n\n"

        "🔹 <b>Bot buyruqlari:</b>\n"
        "/start - Asosiy menyu\n"
        "/help - Yordam\n"
        "/premium - Premium tariflar\n"
        "/stats - Statistika\n"
        "/cancel - Bekor qilish\n\n"

        "🔹 <b>Guruhlarda:</b>\n"
        "Botni guruhga qo'shing va /quiz buyrug'i bilan test boshlang.\n\n"

        "❓ <b>Muammolar:</b> @quizmaster_support\n"
    )
    await message.answer(text, parse_mode=ParseMode.HTML)


@router.message(Command("premium"))
@router.message(F.text.in_({"💎 Premium", "💎 Премиум"}))
async def cmd_premium(message: Message, db_user):
    """Premium tariflari."""
    tier, limits = await subscription_service.get_user_tier(message.from_user.id)
    current = tier.value.upper()

    text = (
        f"💎 <b>Premium tariflar</b>\n\n"
        f"📌 Sizning tarifingiz: <b>{current}</b>\n\n"

        f"<b>🎁 Bepul (FREE):</b>\n"
        f"  • {limits['tests_per_day']} ta test/kun\n"
        f"  • {limits['max_questions']} tagacha savol\n"
        f"  • 10 MB gacha fayl\n\n"

        f"<b>🥉 PRO - 49 900 so'm/oy:</b>\n"
        f"  • 50 ta test/kun\n"
        f"  • 30 tagacha savol\n"
        f"  • 20 MB gacha fayl\n"
        f"  • PDF eksport\n"
        f"  • Batafsil statistika\n\n"

        f"<b>🥈 PREMIUM - 499 000 so'm/yil (17% tejash):</b>\n"
        f"  • 500 ta test/kun\n"
        f"  • 50 tagacha savol\n"
        f"  • 50 MB gacha fayl\n"
        f"  • AI tushuntirishlar\n"
        f"  • Rasmli savollar\n"
        f"  • Marketplace'da ulashish\n\n"

        f"<b>👑 LIFETIME - 999 000 so'm (bir marta):</b>\n"
        f"  • Barchasidan CHEKSIZ foydalanish\n"
        f"  • 100+ savol, 100 MB fayl\n"
        f"  • Barcha yangi funksiyalar\n"
        f"  • VIP qo'llab-quvvatlash\n\n"

        f"💳 To'lov usullari: Telegram Stars, Payme, Click, Uzum\n"
    )

    await message.answer(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=get_premium_keyboard(),
    )


@router.message(Command("stats"))
@router.message(F.text.in_({"📊 Statistika", "📊 Статистика"}))
async def cmd_stats(message: Message, db_user):
    """Foydalanuvchi statistikasi."""
    from bot.db.session import get_session
    from bot.db.models import Test, TestAttempt
    from sqlalchemy import select, func

    async with get_session() as session:
        tests_count = await session.scalar(
            select(func.count(Test.id)).where(Test.user_id == db_user.id)
        )
        attempts_count = await session.scalar(
            select(func.count(TestAttempt.id)).where(TestAttempt.user_id == db_user.id)
        )
        avg_score = await session.scalar(
            select(func.avg(TestAttempt.score_percent)).where(
                TestAttempt.user_id == db_user.id
            )
        )

    text = (
        f"📊 <b>Sizning statistikangiz</b>\n\n"
        f"📚 Yaratilgan testlar: <b>{tests_count or 0}</b>\n"
        f"✅ Yechilgan testlar: <b>{attempts_count or 0}</b>\n"
        f"📈 O'rtacha ball: <b>{(avg_score or 0):.1f}%</b>\n"
        f"🔥 Streak: <b>{db_user.streak_days} kun</b>\n\n"
        f"📅 Ro'yxatdan o'tgan: {db_user.created_at.strftime('%d.%m.%Y')}\n"
    )

    await message.answer(text, parse_mode=ParseMode.HTML)


@router.message(Command("language"))
async def cmd_language(message: Message):
    """Tilni o'zgartirish."""
    await message.answer(
        "🌐 Tilni tanlang:",
        reply_markup=get_language_keyboard(),
    )


@router.callback_query(F.data.startswith("lang_"))
async def cb_language(callback: CallbackQuery, db_user):
    """Tilni o'rnatish."""
    lang = callback.data.split("_")[1]
    if lang not in ("uz", "ru", "en"):
        await callback.answer("❌ Noto'g'ri til")
        return

    db_user.language_code = lang
    await callback.answer(f"✅ Til o'zgartirildi: {lang.upper()}")

    await callback.message.answer(
        f"✅ Til muvaffaqiyatli o'zgartirildi!\n\n"
        f"Quyidagi menyudan foydalaning:",
        reply_markup=get_main_reply_keyboard(lang),
    )


@router.callback_query(F.data == "help")
async def cb_help(callback: CallbackQuery):
    await cmd_help(callback.message)
    await callback.answer()


@router.callback_query(F.data == "premium")
async def cb_premium(callback: CallbackQuery, db_user):
    await cmd_premium(callback.message, db_user)
    await callback.answer()


@router.callback_query(F.data == "back_to_main")
async def cb_back_to_main(callback: CallbackQuery, db_user):
    lang = db_user.language_code if db_user.language_code in ("uz", "ru", "en") else "uz"
    await callback.message.answer(
        "🏠 Asosiy menyu:",
        reply_markup=get_main_reply_keyboard(lang),
    )
    await callback.answer()


@router.callback_query(F.data == "start_trial")
async def cb_start_trial(callback: CallbackQuery, db_user):
    """3 kunlik trial boshlash."""
    if db_user.trial_used:
        await callback.answer(
            "❌ Siz allaqachon trial'dan foydalangansiz",
            show_alert=True,
        )
        return

    success = await subscription_service.start_trial(db_user.id)
    if success:
        await callback.message.answer(
            "🎉 <b>Tabriklaymiz!</b>\n\n"
            "3 kunlik PREMIUM tarifga ega bo'ldingiz! 🎁\n\n"
            "💎 Barcha premium funksiyalar sizga ochiq.\n"
            "⏰ Trial tugagach avtomatik FREE tarifga qaytasiz.",
            parse_mode=ParseMode.HTML,
        )
    else:
        await callback.answer("❌ Xato yuz berdi", show_alert=True)
