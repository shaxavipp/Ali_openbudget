from decimal import Decimal, InvalidOperation

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.callbacks import WithdrawalActionCB
from bot.keyboards import user_kb
from bot.keyboards.user_kb import main_menu
from bot.routers.user.account import WITHDRAW_START_CB
from bot.states.withdrawal_states import WithdrawalStates
from config import settings
from db.models.settings import MIN_WITHDRAWAL
from db.models.user import User
from db.models.withdrawal import PaymentSystem, Withdrawal
from repositories import settings_repo, withdrawal_repo
from services import withdrawal_service
from services.withdrawal_service import InsufficientBalance
from utils.formatting import format_money, mask_card
from utils.timezone import format_local

router = Router(name="user_withdrawal")

PAYMENT_SYSTEM_LABELS = {
    PaymentSystem.HUMO: "🇺🇿 Humo",
    PaymentSystem.UZCARD: "🔵 UzCard",
    PaymentSystem.CLICK: "💠 CLICK",
    PaymentSystem.PAYME: "⬜ PayMe",
    PaymentSystem.PAYNET: "📞 Paynet",
}

CONFIRM_CB = "wd_confirm"
CANCEL_CB = "wd_cancel"


def _format_card(digits: str) -> str:
    """Group raw digits into 4-4-4-4 for display, e.g. '8600 0607 7072 5902'."""
    return " ".join(digits[i : i + 4] for i in range(0, len(digits), 4))


def _payment_system_kb() -> InlineKeyboardMarkup:
    rows = []
    row = []
    for system, label in PAYMENT_SYSTEM_LABELS.items():
        row.append(InlineKeyboardButton(text=label, callback_data=f"wd_sys:{system.value}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _confirm_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=CONFIRM_CB),
                InlineKeyboardButton(text="❌ Bekor qilish", callback_data=CANCEL_CB),
            ]
        ]
    )


def _cancel_only_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="❌ Bekor qilish", callback_data=CANCEL_CB)]]
    )


@router.callback_query(F.data == WITHDRAW_START_CB)
async def withdraw_start(callback: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    min_wd_raw = await settings_repo.get(session, MIN_WITHDRAWAL)
    min_wd = Decimal(min_wd_raw) if min_wd_raw else Decimal("0")
    if db_user.balance < min_wd:
        await callback.answer(
            f"Minimal pul yechish miqdori {format_money(min_wd)}. "
            f"Sizning balansingiz: {format_money(db_user.balance)}.",
            show_alert=True,
        )
        return
    await callback.message.answer("To'lov tizimini tanlang:", reply_markup=_payment_system_kb())
    await callback.answer()


@router.callback_query(F.data.startswith("wd_sys:"))
async def payment_system_chosen(callback: CallbackQuery, state: FSMContext) -> None:
    system_value = callback.data.split(":", 1)[1]
    await state.update_data(payment_system=system_value)
    await state.set_state(WithdrawalStates.waiting_card_number)
    await callback.message.answer(
        "Karta raqamingizni kiriting (16 ta raqam):", reply_markup=_cancel_only_kb()
    )


@router.message(WithdrawalStates.waiting_card_number, F.text, ~F.text.in_(user_kb.MENU_BUTTON_TEXTS))
async def card_number_received(message: Message, state: FSMContext) -> None:
    digits = "".join(ch for ch in message.text if ch.isdigit())
    if len(digits) != 16:
        await message.answer(
            "❗ Karta raqami 16 ta raqamdan iborat bo'lishi kerak. Qayta kiriting:",
            reply_markup=_cancel_only_kb(),
        )
        return
    await state.update_data(card_number=digits)
    await state.set_state(WithdrawalStates.waiting_amount)
    await message.answer(
        "Qancha pul yechib olmoqchisiz? (so'mda kiriting)", reply_markup=_cancel_only_kb()
    )


@router.message(WithdrawalStates.waiting_amount, F.text, ~F.text.in_(user_kb.MENU_BUTTON_TEXTS))
async def amount_received(
    message: Message, session: AsyncSession, state: FSMContext, db_user: User
) -> None:
    try:
        amount = Decimal("".join(ch for ch in message.text if ch.isdigit() or ch == "."))
    except InvalidOperation:
        amount = None

    if amount is None:
        await message.answer("❗ Son kiriting:", reply_markup=_cancel_only_kb())
        return

    min_wd_raw = await settings_repo.get(session, MIN_WITHDRAWAL)
    min_wd = Decimal(min_wd_raw) if min_wd_raw else Decimal("0")

    if amount < min_wd:
        await message.answer(
            f"❗ Minimal summa {format_money(min_wd)}. Qayta kiriting:", reply_markup=_cancel_only_kb()
        )
        return
    if amount > db_user.balance:
        await message.answer(
            f"❗ Balansingizda yetarli mablag' yo'q. Balans: {format_money(db_user.balance)}. Qayta kiriting:",
            reply_markup=_cancel_only_kb(),
        )
        return

    data = await state.get_data()
    await state.update_data(amount=str(amount))
    system_label = PAYMENT_SYSTEM_LABELS[PaymentSystem(data["payment_system"])]
    await message.answer(
        "🧾 So'rovni tekshiring:\n\n"
        f"To'lov tizimi: {system_label}\n"
        f"Karta: {mask_card(data['card_number'])}\n"
        f"Miqdor: {format_money(amount)}",
        reply_markup=_confirm_kb(),
    )


@router.callback_query(F.data == CANCEL_CB)
async def withdraw_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.answer("Bekor qilindi.", reply_markup=main_menu())


@router.callback_query(WithdrawalStates.waiting_amount, F.data == CONFIRM_CB)
async def withdraw_confirm(
    callback: CallbackQuery, session: AsyncSession, state: FSMContext, db_user: User, bot: Bot
) -> None:
    data = await state.get_data()
    try:
        withdrawal = await withdrawal_service.create_withdrawal(
            session,
            db_user,
            payment_system=PaymentSystem(data["payment_system"]),
            card_number=data["card_number"],
            amount=Decimal(data["amount"]),
        )
    except InsufficientBalance:
        await callback.answer("Balansingizda yetarli mablag' yo'q.", show_alert=True)
        await state.clear()
        return

    await state.clear()
    await callback.message.answer(
        "✅ Pul yechish so'rovingiz yuborildi!\n"
        f"To'lov tizimi: {PAYMENT_SYSTEM_LABELS[withdrawal.payment_system]}\n"
        f"Karta: {mask_card(withdrawal.card_number)}\n"
        f"Miqdor: {format_money(withdrawal.amount)}\n\n"
        "Admin tomonidan ko'rib chiqilgach, pul o'tkaziladi.",
        reply_markup=main_menu(),
    )
    await callback.answer()

    await _post_to_payments_channel(session, bot, db_user, withdrawal)


async def _post_to_payments_channel(
    session: AsyncSession, bot: Bot, db_user: User, withdrawal: Withdrawal
) -> None:
    system_icon, _, system_name = PAYMENT_SYSTEM_LABELS[withdrawal.payment_system].partition(" ")
    text = (
        "📝 Yangi pul yechish so'rovi!\n\n"
        f"👤 Foydalanuvchi: {db_user.full_name or '—'} "
        f"(@{db_user.username or '—'}, ID: {db_user.telegram_id})\n"
        f"{system_icon} To'lov tizimi: {system_name}\n"
        f"💳 Karta: {_format_card(withdrawal.card_number)}\n"
        f"💰 Miqdor: {format_money(withdrawal.amount)}\n"
        f"🕒 Vaqt: {format_local(withdrawal.created_at)}"
    )
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ To'landi deb belgilash",
                    callback_data=WithdrawalActionCB(
                        withdrawal_id=withdrawal.id, action="mark_paid"
                    ).pack(),
                )
            ]
        ]
    )
    sent = await bot.send_message(settings.payments_channel_id, text, reply_markup=kb)
    await withdrawal_repo.set_admin_message(session, withdrawal, sent.message_id, sent.chat.id)
