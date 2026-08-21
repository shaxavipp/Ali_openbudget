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
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.user_kb import ACCOUNT_BUTTON, WITHDRAW_BUTTON
from db.models.user import User
from utils.formatting import format_money

logger = logging.getLogger("openbudget")

router = Router(name="user_account")

WITHDRAW_START_CB = "withdraw:start"
MY_WITHDRAWALS_OPEN_CB = "mywithdrawals:open"
ACCOUNT_BACK_CB = "account:back"

# "Shunday bot hohlaysizmi?" tugmasi bosilganda ochiladigan akkaunt.
PROMO_BOT_URL = "https://t.me/shaxavip"

# Profil kartochkasi tepasidagi logotip — account.py bilan bir papkada (bot/routers/user/).
ACCOUNT_PHOTO_PATH = Path(__file__).parent / "openbudget_logo.jpg"


def _account_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=WITHDRAW_BUTTON, callback_data=WITHDRAW_START_CB),
                InlineKeyboardButton(text="📋 Sizning tarix", callback_data=MY_WITHDRAWALS_OPEN_CB),
            ],
            [InlineKeyboardButton(text="🚀 Shunday bot hohlaysizmi?", url=PROMO_BOT_URL)],
        ]
    )


def _account_text(db_user: User) -> str:
    return (
        "💻 Profilingiz haqida ma'lumot:\n\n"
        f"📝 Ismingiz: {db_user.full_name or '—'}\n"
        f"🆔 ID raqamingiz: {db_user.telegram_id}\n"
        "―" * 20 + "\n\n"
        f"💰 Sizning balansingiz: {format_money(db_user.balance)}\n"
        f"💸 Yechilgan summa: {format_money(db_user.total_withdrawn)}\n"
        f"🗳 Siz bergan ovozlar: {db_user.votes_confirmed_count} ta"
    )


async def _send_account_card(answer_photo, answer_text, db_user: User) -> None:
    """Try to send the account card with the logo photo; fall back to plain text
    if the photo can't be sent (missing file, permission issue, etc.) so the
    "Hisobim" section never fully breaks — and log the real reason either way."""
    try:
        await answer_photo(
            FSInputFile(ACCOUNT_PHOTO_PATH),
            caption=_account_text(db_user),
            reply_markup=_account_kb(),
        )
    except Exception:
        logger.exception(
            "Akkaunt logotipini yuborib bo'lmadi (yo'l: %s). Matnli ko'rinishga o'tildi.",
            ACCOUNT_PHOTO_PATH,
        )
        await answer_text(_account_text(db_user), reply_markup=_account_kb())


@router.message(F.text == ACCOUNT_BUTTON)
async def show_account(message: Message, session: AsyncSession, db_user: User, state: FSMContext) -> None:
    await state.clear()
    await _send_account_card(message.answer_photo, message.answer, db_user)


@router.callback_query(F.data == ACCOUNT_BACK_CB)
async def back_to_account(callback: CallbackQuery, db_user: User) -> None:
    # Manba xabar (masalan "to'lovlar tarixi") oddiy matn bo'lgani uchun uni to'g'ridan-to'g'ri
    # rasmli xabarga aylantirib bo'lmaydi — shuning uchun eskisini o'chirib, o'rniga yangi
    # akkaunt kartasini yuboramiz.
    try:
        await callback.message.delete()
    except TelegramBadRequest:
        pass
    await _send_account_card(callback.message.answer_photo, callback.message.answer, db_user)
