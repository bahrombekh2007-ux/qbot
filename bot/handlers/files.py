"""Fayl yuklash va test yaratish handlerlari."""
import os
import uuid
import logging
from pathlib import Path
from datetime import datetime

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, FSInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.enums import ParseMode

from bot.config import settings
from bot.services.parser import FileParser
from bot.services.ai import ai_service
from bot.services.subscription import subscription_service
from bot.db.session import get_session
from bot.db.models import Test, TestStatus
from bot.keyboards import get_quiz_settings_keyboard
from sqlalchemy import select

logger = logging.getLogger(__name__)
router = Router(name="files")

# Foydalanuvchiga xos vaqtinchalik ma'lumotlar (production da Redis ga ko'chiriladi)
# Format: {user_id: {"text": "...", "filename": "...", "ext": "..."}}
from cachetools import TTLCache
user_uploads: dict = TTLCache(maxsize=10_000, ttl=3600)


class QuizCreation(StatesGroup):
    """FSM - test yaratish jarayoni."""
    waiting_file = State()
    waiting_settings = State()
    processing = State()


@router.message(F.document)
async def handle_document(message: Message, state: FSMContext, db_user):
    """Fayl qabul qilish."""
    document = message.document
    user = message.from_user

    # Limit tekshirish
    if document.file_size and document.file_size > settings.max_file_size_mb * 1024 * 1024:
        await message.answer(
            f"❌ Fayl hajmi katta. Maksimal: {settings.max_file_size_mb} MB\n"
            f"Siz yuborgan: {document.file_size / 1024 / 1024:.1f} MB",
        )
        return

    # Format tekshirish
    file_ext = FileParser.detect_format(document.file_name or "")
    if not file_ext:
        await message.answer(
            "❌ Qo'llab-quvvatlanmaydigan format.\n\n"
            "✅ Qo'llab-quvvatlanadigan: PDF, DOC, DOCX, XLSX, TXT, PPTX"
        )
        return

    # Subscription limit
    allowed, reason, stats = await subscription_service.check_quota(
        user.id, db_user.id
    )
    if not allowed:
        await message.answer(reason, parse_mode=ParseMode.HTML)
        return

    # Processing xabari
    status_msg = await message.answer("⏳ Fayl yuklanmoqda...")

    try:
        # Yuklash
        file = await message.bot.get_file(document.file_id)
        unique_name = f"{user.id}_{uuid.uuid4().hex[:8]}_{document.file_name}"
        file_path = settings.upload_path / unique_name

        await message.bot.download_file(file.file_path, destination=file_path)

        # Parse qilish
        await status_msg.edit_text("📄 Fayl o'qilmoqda...")

        text = await FileParser.extract_text(file_path, file_ext)
        stats_data = FileParser.get_file_stats(text)

        if not text or len(text.strip()) < 100:
            await status_msg.edit_text(
                "❌ Faylda yetarli matn topilmadi.\n"
                "Iltimos, boshqa fayl yuklang."
            )
            return

        # Tilni aniqlash
        lang = await ai_service.detect_language(text)

        # Vaqtinchalik saqlash
        user_uploads[user.id] = {
            "text": text,
            "filename": document.file_name,
            "ext": file_ext,
            "lang": lang,
            "stats": stats_data,
        }

        # Sozlamalarni so'rash
        await state.set_state(QuizCreation.waiting_settings)

        limits = subscription_service.get_tier_limits(
            (await subscription_service.get_user_tier(user.id))[0]
        )

        await status_msg.edit_text(
            f"✅ <b>Fayl muvaffaqiyatli yuklandi!</b>\n\n"
            f"📄 Nomi: {document.file_name}\n"
            f"📊 Hajmi: {stats_data['chars']:,} belgi, {stats_data['words']:,} so'z\n"
            f"🌐 Til: {lang.upper()}\n\n"
            f"⚙️ <b>Test sozlamalarini tanlang:</b>\n"
            f"(Sizning tarifingiz: {stats['tier'].upper()}, "
            f"max {limits['max_questions']} savol)",
            parse_mode=ParseMode.HTML,
            reply_markup=get_quiz_settings_keyboard(),
        )

    except Exception as e:
        logger.exception("File processing error")
        await status_msg.edit_text(
            f"❌ Faylni qayta ishlashda xato: {str(e)[:200]}"
        )


@router.callback_query(F.data.startswith("count_"))
async def cb_set_count(callback: CallbackQuery):
    """Savollar sonini tanlash."""
    count = int(callback.data.split("_")[1])
    user_id = callback.from_user.id

    if user_id not in user_uploads:
        await callback.answer("❌ Avval fayl yuklang", show_alert=True)
        return

    user_uploads[user_id]["count"] = count
    await callback.answer(f"✅ {count} ta savol tanlandi")


@router.callback_query(F.data.startswith("diff_"))
async def cb_set_difficulty(callback: CallbackQuery):
    """Qiyinlik darajasini tanlash."""
    diff = callback.data.split("_")[1]
    user_id = callback.from_user.id

    if user_id not in user_uploads:
        await callback.answer("❌ Avval fayl yuklang", show_alert=True)
        return

    user_uploads[user_id]["difficulty"] = diff
    difficulty_names = {"easy": "oson", "medium": "o'rta", "hard": "qiyin", "mixed": "aralash"}
    await callback.answer(f"✅ Qiyinlik: {difficulty_names.get(diff, diff)}")


@router.callback_query(F.data == "generate_quiz")
async def cb_generate_quiz(callback: CallbackQuery, state: FSMContext, db_user):
    """Test yaratishni boshlash."""
    user_id = callback.from_user.id

    if user_id not in user_uploads:
        await callback.answer("❌ Avval fayl yuklang", show_alert=True)
        return

    upload = user_uploads[user_id]
    count = upload.get("count", 10)
    difficulty = upload.get("difficulty", "mixed")
    lang = upload.get("lang", "uz")

    # Tariff limitini tekshirish
    tier, limits = await subscription_service.get_user_tier(user_id)
    if count > limits["max_questions"]:
        count = limits["max_questions"]

    await callback.message.edit_text(
        f"🤖 <b>AI savollar yaratmoqda...</b>\n\n"
        f"Savollar soni: {count}\n"
        f"Qiyinlik: {difficulty}\n\n"
        f"⏳ Bu 10-30 soniya vaqt olishi mumkin...",
        parse_mode=ParseMode.HTML,
    )

    try:
        # AI orqali generatsiya
        questions = await ai_service.generate_questions(
            upload["text"],
            count=count,
            language=lang,
            difficulty=difficulty,
        )

        # Bazaga saqlash
        from bot.db.session import get_session
        from bot.db.models import Test, TestStatus
        from sqlalchemy import select

        async with get_session() as session:
            test = Test(
                user_id=db_user.id,
                title=Path(upload["filename"]).stem or "Test",
                source_file=upload["filename"],
                source_type=upload["ext"],
                questions={"items": questions, "version": 1},
                total_questions=len(questions),
                status=TestStatus.READY,
            )
            session.add(test)
            await session.commit()
            await session.refresh(test)
            test_id = test.id

        # Usage +1
        await subscription_service.increment_usage(db_user.id, len(questions))

        # WebApp ga yo'naltirish
        from bot.config import settings
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo

        kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🎯 Testni boshlash",
                    web_app=WebAppInfo(url=f"{settings.webapp_url}?action=take&test_id={test_id}"),
                )
            ],
            [
                InlineKeyboardButton(
                    text="📤 Ulashish",
                    switch_inline_query=f"test_{test_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="📚 Mening testlarim",
                    web_app=WebAppInfo(url=f"{settings.webapp_url}?action=my"),
                )
            ],
        ])

        await callback.message.edit_text(
            f"🎉 <b>Test tayyor!</b>\n\n"
            f"📝 Savollar: {len(questions)} ta\n"
            f"📊 Qiyinlik: {difficulty}\n\n"
            f"Quyidagi tugma orqali testni boshlang:",
            parse_mode=ParseMode.HTML,
            reply_markup=kb,
        )

        # State tozalash
        await state.clear()
        user_uploads.pop(user_id, None)

    except Exception as e:
        logger.exception("Quiz generation error")
        await callback.message.edit_text(
            f"❌ Test yaratishda xato: {str(e)[:200]}\n\n"
            f"Iltimos qaytadan urinib ko'ring."
        )


@router.callback_query(F.data == "cancel")
async def cb_cancel(callback: CallbackQuery, state: FSMContext):
    """Bekor qilish."""
    user_uploads.pop(callback.from_user.id, None)
    await state.clear()
    await callback.message.edit_text("❌ Bekor qilindi")
    await callback.answer()


# ============== Guruhlar uchun ==============

@router.message(F.text.startswith("/quiz"))
async def cmd_quiz_group(message: Message):
    """Guruhda test yaratish."""
    if message.chat.type == "private":
        return

    await message.answer(
        "📝 Guruhda test yaratish uchun:\n"
        "1. Botga shaxsiy xabar yuboring\n"
        "2. Fayl yuklang\n"
        "3. Yaratilgan testni shu guruhga ulashing\n\n"
        "💡 Tez orada guruh uchun ham to'g'ridan-to'g'ri test yaratish funksiyasi qo'shiladi!"
    )
