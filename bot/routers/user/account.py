import asyncio
import logging
from pathlib import Path

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.user_kb import ACCOUNT_BUTTON, WITHDRAW_BUTTON
from db.models.referral import Referral
from db.models.user import User
from utils.formatting import format_money

logger = logging.getLogger("openbudget")

router = Router(name="user_account")

WITHDRAW_START_CB = "withdraw:start"
MY_WITHDRAWALS_OPEN_CB = "mywithdrawals:open"
ACCOUNT_BACK_CB = "account:back"

# "Shunday bot hohlaysizmi?" tugmasi bosilganda ochiladigan akkaunt.
PROMO_BOT_URL = "https://t.me/shaxavip"

# Profil kartochkasi tepasidagi logotip — shu fayl repo ichida, account.py bilan
# bir papkada (bot/routers/user/openbudget_logo.jpg) bo'lishi SHART, aks holda
# rasm yuborilmaydi va matnli ko'rinishga tushib qolinadi. Fayl mavjudligini
# deploy qilishdan oldin tekshiring: `git ls-files | grep openbudget_logo`.
ACCOUNT_PHOTO_PATH = Path(__file__).parent / "openbudget_logo.jpg"

# --- Bitta foydalanuvchi uchun bitta "jonli" akkaunt kartasi ---
#
# "Hisobim" — reply-keyboard tugmasi, shuning uchun har bosilganda Telegram uni
# yangi, mustaqil xabar sifatida yuboradi (bu bot emas, Telegram shunday
# ishlaydi). Har bosishga foydalanuvchiga ANIQ KO'RINADIGAN javob kerak
# (shunchaki jim turib qolmaslik kerak) — shu bilan birga ekranda bir xil
# karta bir necha nusxada birga to'planib qolmasligi ham kerak.
#
# Shu ikkalasini birga ta'minlash uchun: har safar avvalgi karta (agar
# mavjud bo'lsa) avval O'CHIRILADI, so'ng o'rniga YANGI karta yuboriladi.
# Natijada: (a) har bosish uchun ko'zga ko'rinadigan yangi xabar bo'ladi —
# hattoki balans o'zgarmagan bo'lsa ham, (b) bir vaqtning o'zida ekranda
# faqat BITTA karta bo'ladi, chunki eskisi yangisi yuborilishidan oldin
# yo'q qilinadi.
#
# Birinchi muvaffaqiyatli yuborishdan keyin Telegram bergan file_id shu yerda
# keshlanadi — shundan keyin rasm diskdan qayta yuklanmaydi, file_id orqali
# darhol yuboriladi (tezroq va ishonchli).
_last_message: dict[int, tuple[int, int]] = {}  # user_id -> (chat_id, message_id)
_locks: dict[int, asyncio.Lock] = {}
_cached_photo_id: str | None = None


def _lock_for(user_id: int) -> asyncio.Lock:
    lock = _locks.get(user_id)
    if lock is None:
        lock = asyncio.Lock()
        _locks[user_id] = lock
    return lock


def _account_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=WITHDRAW_BUTTON, callback_data=WITHDRAW_START_CB)],
            [InlineKeyboardButton(text="📋 Sizning tarix", callback_data=MY_WITHDRAWALS_OPEN_CB)],
            [InlineKeyboardButton(text="🚀 Shunday bot hohlaysizmi?", url=PROMO_BOT_URL)],
        ]
    )


async def _count_referrals(session: AsyncSession, user_id: int) -> int:
    stmt = select(func.count()).select_from(Referral).where(Referral.referrer_id == user_id)
    return (await session.execute(stmt)).scalar() or 0


def _account_caption(db_user: User, referral_count: int) -> str:
    return (
        "💻 Profilingiz haqida ma'lumot:\n\n"
        f"📝 Ismingiz: {db_user.full_name or '—'}\n"
        f"🆔 ID raqamingiz: {db_user.telegram_id}\n\n"
        f"💰 Sizning balansingiz: {format_money(db_user.balance)}\n"
        f"💸 Yechilgan summa: {format_money(db_user.total_withdrawn)}\n"
        f"🗳 Siz bergan ovozlar: {db_user.votes_confirmed_count} ta\n"
        f"👥 Takliflaringiz: {referral_count} ta"
    )


async def _show_or_refresh_account(
    bot, chat_id: int, session: AsyncSession, db_user: User
) -> None:
    """Foydalanuvchining akkaunt kartasini ko'rsatadi: avvalgi kartani
    o'chirib, o'rniga yangisini yuboradi — shunda har bosish ko'rinadigan
    javob oladi, lekin ekranda hech qachon bir nechta nusxa birga turmaydi."""
    global _cached_photo_id
    async with _lock_for(db_user.telegram_id):
        referral_count = await _count_referrals(session, db_user.telegram_id)
        caption = _account_caption(db_user, referral_count)
        kb = _account_kb()

        existing = _last_message.get(db_user.telegram_id)
        if existing is not None:
            existing_chat_id, existing_message_id = existing
            try:
                await bot.delete_message(chat_id=existing_chat_id, message_id=existing_message_id)
            except TelegramBadRequest:
                # Eski xabar allaqachon o'chirilgan yoki o'chirib bo'lmaydi —
                # baribir yangisini yuboramiz.
                pass

        try:
            sent = await bot.send_photo(
                chat_id,
                _cached_photo_id or FSInputFile(ACCOUNT_PHOTO_PATH),
                caption=caption,
                reply_markup=kb,
            )
            if _cached_photo_id is None and sent.photo:
                _cached_photo_id = sent.photo[-1].file_id
        except Exception:
            logger.exception(
                "Akkaunt logotipini yuborib bo'lmadi (yo'l: %s). Matnli ko'rinishga o'tildi.",
                ACCOUNT_PHOTO_PATH,
            )
            sent = await bot.send_message(chat_id, caption, reply_markup=kb)

        _last_message[db_user.telegram_id] = (sent.chat.id, sent.message_id)


@router.message(F.text == ACCOUNT_BUTTON)
async def show_account(message: Message, session: AsyncSession, db_user: User, state: FSMContext) -> None:
    await state.clear()
    await _show_or_refresh_account(message.bot, message.chat.id, session, db_user)


@router.callback_query(F.data == ACCOUNT_BACK_CB)
async def back_to_account(callback: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    await _show_or_refresh_account(callback.message.bot, callback.message.chat.id, session, db_user)
    await callback.answer()
