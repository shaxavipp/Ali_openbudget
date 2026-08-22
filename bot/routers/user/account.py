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
# ishlaydi). Buning ustiga bir necha marta bosilganda ekranda bir xil karta
# ko'payib ketmasligi uchun ikkita himoya qo'llanadi:
#
#   1. Har bir foydalanuvchi uchun oxirgi yuborilgan kartaning manzili
#      (chat_id, message_id) xotirada saqlanadi, va keyingi har qanday
#      chaqiruvda YANGI xabar yuborish o'rniga O'SHA XABAR TAHRIRLANADI.
#   2. Agar tahrirlashda Telegram "message is not modified" xatosini
#      qaytarsa (matn/rasm/tugmalar OLDINGISI BILAN AYNAN BIR XIL bo'lganda —
#      masalan balans o'zgarmagan holda qayta bosilganda) — bu haqiqiy xato
#      emas, karta allaqachon to'g'ri holatda, shuning uchun hech narsa
#      qilinmaydi. Buni oddiy xato deb hisoblab "yangi xabar yuborish"ga
#      tushib qolish — aynan shu joyning o'zi eski nusxada bir xil kartaning
#      bir necha marta takrorlanib chiqishiga sabab bo'lgan edi.
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
    """Foydalanuvchining akkaunt kartasini ko'rsatadi: agar avval yuborilgan
    kartasi hali mavjud bo'lsa uni tahrirlaydi, aks holda yangisini yuboradi."""
    global _cached_photo_id
    async with _lock_for(db_user.telegram_id):
        referral_count = await _count_referrals(session, db_user.telegram_id)
        caption = _account_caption(db_user, referral_count)
        kb = _account_kb()

        existing = _last_message.get(db_user.telegram_id)
        if existing is not None:
            existing_chat_id, existing_message_id = existing
            try:
                await bot.edit_message_caption(
                    chat_id=existing_chat_id,
                    message_id=existing_message_id,
                    caption=caption,
                    reply_markup=kb,
                )
                return
            except TelegramBadRequest as e:
                if "message is not modified" in str(e).lower():
                    return
                # Boshqa sabab bilan tahrirlab bo'lmadi (masalan xabar o'chirilgan,
                # yoki u rasmli xabar emas edi) — yangisini yuborishga o'tamiz.

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
