"""To'lov va premium handlerlari."""
import logging
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, LabeledPrice
from aiogram.enums import ParseMode

from bot.config import settings
from bot.services.subscription import subscription_service, SubscriptionTier
from bot.db.models import Payment
from bot.db.session import get_session
from sqlalchemy import select

logger = logging.getLogger(__name__)
router = Router(name="payments")


PREMIUM_PLANS = {
    "pro_monthly": {
        "tier": SubscriptionTier.PRO,
        "title": "PRO - 1 oy",
        "description": "Kengaytirilgan imkoniyatlar",
        "amount": settings.premium_monthly_price,  # tiyin
        "duration_days": 30,
        "stars": 350,  # Telegram Stars
    },
    "premium_yearly": {
        "tier": SubscriptionTier.PREMIUM,
        "title": "PREMIUM - 1 yil",
        "description": "Eng yaxshi tarif - 17% tejash",
        "amount": settings.premium_yearly_price,
        "duration_days": 365,
        "stars": 3500,
    },
    "lifetime": {
        "tier": SubscriptionTier.LIFETIME,
        "title": "LIFETIME",
        "description": "Bir marta to'lov, cheksiz foydalanish",
        "amount": settings.premium_lifetime_price,
        "duration_days": 36500,  # 100 yil
        "stars": 7000,
    },
}


@router.callback_query(F.data.startswith("buy_"))
async def cb_buy(callback: CallbackQuery, db_user):
    """Tarif sotib olish - to'lov usulini tanlash."""
    plan = callback.data.replace("buy_", "")

    if plan not in PREMIUM_PLANS:
        await callback.answer("❌ Noma'lum tarif", show_alert=True)
        return

    plan_info = PREMIUM_PLANS[plan]

    text = (
        f"💎 <b>{plan_info['title']}</b>\n\n"
        f"📝 {plan_info['description']}\n\n"
        f"💰 Narx: <b>{plan_info['amount']:,} so'm</b>\n"
        f"⭐ Yoki: <b>{plan_info['stars']} Telegram Stars</b>\n\n"
        f"To'lov usulini tanlang:"
    )

    from bot.keyboards import get_payment_method_keyboard
    await callback.message.edit_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=get_payment_method_keyboard(plan),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("pay_stars_"))
async def cb_pay_stars(callback: CallbackQuery, db_user):
    """Telegram Stars orqali to'lov."""
    plan = callback.data.replace("pay_stars_", "")
    if plan not in PREMIUM_PLANS:
        await callback.answer("❌ Noma'lum tarif")
        return

    plan_info = PREMIUM_PLANS[plan]

    # Telegram Stars invoice
    prices = [LabeledPrice(label=plan_info["title"], amount=plan_info["stars"])]

    try:
        await callback.bot.send_invoice(
            chat_id=callback.from_user.id,
            title=plan_info["title"],
            description=plan_info["description"],
            payload=f"plan:{plan}:user:{db_user.id}",
            provider_token="",  # Stars uchun bo'sh
            currency="XTR",  # Telegram Stars kodi
            prices=prices,
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Stars invoice error: {e}")
        await callback.answer("❌ Xatolik yuz berdi", show_alert=True)


@router.pre_checkout_query()
async def process_pre_checkout(pre_checkout_query):
    """Stars to'lovdan oldin tekshirish."""
    await pre_checkout_query.bot.answer_pre_checkout_query(
        pre_checkout_query.id, ok=True
    )


@router.message(F.successful_payment)
async def process_successful_payment(message: Message, db_user):
    """Telegram Stars to'lov muvaffaqiyatli."""
    payment = message.successful_payment
    payload = payment.invoice_payload  # "plan:premium_yearly:user:123"

    try:
        parts = payload.split(":")
        plan = parts[1]
        user_id = int(parts[3])

        if user_id != db_user.id:
            logger.warning(f"Payment user mismatch: {user_id} vs {db_user.id}")
            return

        plan_info = PREMIUM_PLANS[plan]

        # Tarifni yangilash
        await subscription_service.upgrade_tier(
            db_user.id,
            plan_info["tier"],
            plan_info["duration_days"],
        )

        # To'lov tarixini saqlash
        async with get_session() as session:
            p = Payment(
                user_id=db_user.id,
                amount=payment.total_amount,
                currency="XTR",
                provider="telegram_stars",
                plan=plan,
                external_id=payment.telegram_payment_charge_id,
                status="paid",
                payload=payload,
            )
            session.add(p)

        # Muvaffaqiyat xabari
        await message.answer(
            f"🎉 <b>Tabriklaymiz!</b>\n\n"
            f"Siz muvaffaqiyatli <b>{plan_info['title']}</b> tarifini sotib oldingiz!\n\n"
            f"💎 Barcha premium funksiyalar ochildi.\n"
            f"⏰ Amal qilish muddati: {plan_info['duration_days']} kun\n\n"
            f"Test yaratishni boshlashingiz mumkin! 👇",
            parse_mode=ParseMode.HTML,
        )

        logger.info(f"User {db_user.id} upgraded to {plan_info['tier'].value} via Stars")

    except Exception as e:
        logger.exception(f"Payment processing error: {e}")
        await message.answer("❌ To'lovni qayta ishlashda xato. Support: @quizmaster_support")


# ============== Payme / Click uchun ==============

@router.callback_query(F.data.startswith("pay_payme_"))
async def cb_pay_payme(callback: CallbackQuery, db_user):
    """Payme orqali to'lov (O'zbekiston)."""
    plan = callback.data.replace("pay_payme_", "")

    if plan not in PREMIUM_PLANS:
        await callback.answer("❌ Xato")
        return

    plan_info = PREMIUM_PLANS[plan]
    amount_uzs = plan_info["amount"] / 100  # tiyin -> so'm

    # Payme Checkout URL yaratish
    # Real production'da: Payme Merchant API dan foydalaning
    # Hozircha demo URL

    text = (
        f"💳 <b>Payme orqali to'lov</b>\n\n"
        f"📋 Tarif: {plan_info['title']}\n"
        f"💰 Summa: {amount_uzs:,.0f} so'm\n\n"

        f"📲 <b>To'lov qilish:</b>\n"
        f"1. Payme ilovasini oching\n"
        f"2. Quyidagi ID orqali to'lang\n"
        f"3. Yoki tugmani bosing\n\n"
        f"🔑 To'lov ID: <code>quiz_{db_user.id}_{plan}</code>"
    )

    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

    # Bu yerda haqiqiy Payme Checkout URL bo'lishi kerak
    payme_url = (
        f"https://checkout.paycom.uz/"
        f"?merchant_id={settings.provider_payme or 'demo'}&"
        f"amount={plan_info['amount']}&"
        f"account[order_id]={db_user.id}_{plan}"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Payme'da to'lash", url=payme_url)],
        [InlineKeyboardButton(text="✅ To'lov qildim", callback_data=f"check_payme_{plan}")],
        [InlineKeyboardButton(text="🔙 Orqaga", callback_data=f"buy_{plan}")],
    ])

    await callback.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data.startswith("pay_click_"))
async def cb_pay_click(callback: CallbackQuery, db_user):
    """Click orqali to'lov (O'zbekiston)."""
    plan = callback.data.replace("pay_click_", "")

    if plan not in PREMIUM_PLANS:
        await callback.answer("❌ Xato")
        return

    plan_info = PREMIUM_PLANS[plan]
    amount_uzs = plan_info["amount"] / 100

    text = (
        f"💳 <b>Click orqali to'lov</b>\n\n"
        f"📋 Tarif: {plan_info['title']}\n"
        f"💰 Summa: {amount_uzs:,.0f} so'm\n\n"
        f"📲 <b>To'lov qilish:</b>\n"
        f"Click ilovasidan to'lov ID: <code>quiz_{db_user.id}_{plan}</code>"
    )

    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

    click_url = (
        f"https://my.click.uz/services/pay?"
        f"service_id={settings.provider_click or 'demo'}&"
        f"amount={amount_uzs}&"
        f"transaction_param=quiz_{db_user.id}_{plan}"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Click'da to'lash", url=click_url)],
        [InlineKeyboardButton(text="✅ To'lov qildim", callback_data=f"check_click_{plan}")],
        [InlineKeyboardButton(text="🔙 Orqaga", callback_data=f"buy_{plan}")],
    ])

    await callback.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data.startswith("check_payme_"))
async def cb_check_payme(callback: CallbackQuery, db_user):
    """Payme to'lovini tekshirish (demo - real'da API orqali)."""
    await callback.answer(
        "⏳ To'lov tekshirilmoqda...\n\n"
        "Demo rejim: haqiqiy to'lov bir necha daqiqada qabul qilinadi.\n"
        "Production'da bu avtomatik ishlaydi.",
        show_alert=True,
    )
