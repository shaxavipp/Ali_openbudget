import asyncio

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

# --- Bitta foydalanuvchi uchun bitta "jonli" akkaunt kartasi ---
#
# "Hisobim" — reply-keyboard tugmasi, shuning uchun har bosilganda Telegram uni
# yangi, mustaqil matnli xabar sifatida yuboradi (bu bot tomonidan emas, Telegram
# tomonidan shunday ishlaydi). Foydalanuvchi tugmani tez-tez bir necha marta bossa,
# har bir bosish alohida update bo'lib keladi va — eski yondashuvda — har biriga
# alohida YANGI xabar yuborilar edi, natijada bir xil kartochka bir necha marta
# ekranda qolib ketardi.
#
# Buning oldini olish uchun endi har bir foydalanuvchi uchun oxirgi yuborilgan
# akkaunt xabarining (chat_id, message_id) manzili xotirada saqlanadi. Keyingi
# har qanday chaqiruvda (qayta bosish bo'ladimi, "orqaga" tugmasi bo'ladimi) bot
# YANGI xabar yubormaydi — mavjud xabarni TAHRIRLAYDI. Shu tufayli ekranda hech
# qachon bir nechta nusxa to'planib qolmaydi, tugma necha marta bosilishidan
# qat'i nazar.
#
# Har bir foydalanuvchi uchun alohida asyncio.Lock bilan amallar ketma-ket
# (bittadan) bajarilishi ta'minlanadi — parallel ikki chaqiruv bir-birining
# ustidan yozib, xabar holatini chalkashtirib yubormasligi uchun.
_last_message: dict[int, tuple[int, int]] = {}  # user_id -> (chat_id, message_id)
_locks: dict[int, asyncio.Lock] = {}


def _lock_for(user_id: int) -> asyncio.Lock:
    lock = _locks.get(user_id)
    if lock is None:
        lock = asyncio.Lock()
        _locks[user_id] = lock
    return lock


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


async def _show_or_refresh_account(bot, chat_id: int, db_user: User) -> None:
    """Foydalanuvchining akkaunt kartasini ko'rsatadi: agar avval yuborilgan
    kartasi hali mavjud bo'lsa uni tahrirlaydi, aks holda yangisini yuboradi."""
    async with _lock_for(db_user.telegram_id):
        text = _account_text(db_user)
        kb = _account_kb()

        existing = _last_message.get(db_user.telegram_id)
        if existing is not None:
            existing_chat_id, existing_message_id = existing
            try:
                await bot.edit_message_text(
                    text, chat_id=existing_chat_id, message_id=existing_message_id, reply_markup=kb
                )
                return
            except TelegramBadRequest:
                # Eski xabar tahrirlab bo'lmaydi (o'chirilgan, matn bir xil, yoki
                # boshqa sabab) — yangisini yuborishga o'tamiz.
                pass

        sent = await bot.send_message(chat_id, text, reply_markup=kb)
        _last_message[db_user.telegram_id] = (sent.chat.id, sent.message_id)


@router.message(F.text == ACCOUNT_BUTTON)
async def show_account(message: Message, session: AsyncSession, db_user: User, state: FSMContext) -> None:
    await state.clear()
    await _show_or_refresh_account(message.bot, message.chat.id, db_user)


@router.callback_query(F.data == ACCOUNT_BACK_CB)
async def back_to_account(callback: CallbackQuery, db_user: User) -> None:
    await _show_or_refresh_account(callback.message.bot, callback.message.chat.id, db_user)
    await callback.answer()
