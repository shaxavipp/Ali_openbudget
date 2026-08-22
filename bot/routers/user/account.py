import time

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
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

# "Hisobim" reply-tugmasi bosilganda har safar YANGI matnli xabar sifatida keladi
# (inline tugma emas), shuning uchun foydalanuvchi bir necha marta tez-tez bossa,
# har biriga alohida javob yuborilar edi va bir xil kartochka bir necha marta
# takrorlanib ko'rinardi. Buni oldini olish uchun har bir foydalanuvchi uchun
# qisqa "sovish" (debounce) oynasi qo'llanadi — shu oyna ichidagi qayta bosishlar
# e'tiborsiz qoldiriladi.
_DEBOUNCE_SECONDS = 2.0
_last_press: dict[int, float] = {}


def _is_debounced(user_id: int) -> bool:
    now = time.monotonic()
    last = _last_press.get(user_id)
    _last_press[user_id] = now
    return last is not None and (now - last) < _DEBOUNCE_SECONDS


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
    if _is_debounced(db_user.telegram_id):
        return
    await state.clear()
    await message.answer(_account_text(db_user), reply_markup=_account_kb())


@router.callback_query(F.data == ACCOUNT_BACK_CB)
async def back_to_account(callback: CallbackQuery, db_user: User) -> None:
    try:
        await callback.message.edit_text(_account_text(db_user), reply_markup=_account_kb())
    except TelegramBadRequest:
        # Manba xabar tahrirlab bo'lmaydigan turdagi bo'lsa (masalan boshqa xabar turi),
        # eskisini o'chirib, o'rniga yangi akkaunt kartasini yuboramiz.
        try:
            await callback.message.delete()
        except TelegramBadRequest:
            pass
        await callback.message.answer(_account_text(db_user), reply_markup=_account_kb())
