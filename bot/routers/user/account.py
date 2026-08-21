from pathlib import Path

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.user_kb import ACCOUNT_BUTTON, WITHDRAW_BUTTON
from db.models.user import User
from utils.formatting import format_money

router = Router(name="user_account")

WITHDRAW_START_CB = "withdraw:start"
MY_WITHDRAWALS_OPEN_CB = "mywithdrawals:open"
ACCOUNT_BACK_CB = "account:back"

# "Shunday bot hohlaysizmi?" tugmasi bosilganda ochiladigan akkaunt.
PROMO_BOT_URL = "https://t.me/shaxavip"

# Profil kartochkasi tepasidagi logotip. Loyihangizda fayl boshqa joyda bo'lsa shu yo'lni tuzating.
ACCOUNT_PHOTO_PATH = Path("assets/openbudget_logo.jpg")


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


@router.message(F.text == ACCOUNT_BUTTON)
async def show_account(message: Message, session: AsyncSession, db_user: User, state: FSMContext) -> None:
    await state.clear()
    await message.answer_photo(
        FSInputFile(ACCOUNT_PHOTO_PATH),
        caption=_account_text(db_user),
        reply_markup=_account_kb(),
    )


@router.callback_query(F.data == ACCOUNT_BACK_CB)
async def back_to_account(callback: CallbackQuery, db_user: User) -> None:
    # Manba xabar (masalan "to'lovlar tarixi") oddiy matn bo'lgani uchun uni to'g'ridan-to'g'ri
    # rasmli xabarga aylantirib bo'lmaydi — shuning uchun eskisini o'chirib, o'rniga yangi
    # rasmli akkaunt kartasini yuboramiz.
    try:
        await callback.message.delete()
    except TelegramBadRequest:
        pass
    await callback.message.answer_photo(
        FSInputFile(ACCOUNT_PHOTO_PATH),
        caption=_account_text(db_user),
        reply_markup=_account_kb(),
    )
