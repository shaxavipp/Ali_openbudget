from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.callbacks import AdminMenuCB
from bot.filters import IsAdmin
from bot.keyboards import admin_kb
from bot.states.settings_states import GlobalSettingsStates
from db.models.settings import DONAT_ACCOUNT, MIN_WITHDRAWAL, VOTE_PRICE
from repositories import settings_repo
from utils.formatting import format_money

router = Router(name="admin_global_settings")
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())

EDIT_PRICE_CB = "gs_edit:vote_price"
EDIT_MIN_WD_CB = "gs_edit:min_withdrawal"
EDIT_DONAT_CB = "gs_edit:donat_account"


def _settings_kb():
    return admin_kb.with_back_row(
        [
            [InlineKeyboardButton(text="💰 Ovoz narxini o'zgartirish", callback_data=EDIT_PRICE_CB)],
            [
                InlineKeyboardButton(
                    text="🧾 Minimal pul yechish miqdorini o'zgartirish",
                    callback_data=EDIT_MIN_WD_CB,
                )
            ],
            [
                InlineKeyboardButton(
                    text="🎮 Donat hisobini o'zgartirish",
                    callback_data=EDIT_DONAT_CB,
                )
            ],
        ]
    )


async def _render(session: AsyncSession) -> str:
    values = await settings_repo.get_all(session)
    price = values.get(VOTE_PRICE, "0")
    min_wd = values.get(MIN_WITHDRAWAL, "0")
    donat_account = values.get(DONAT_ACCOUNT, "Hali sozlanmagan")
    return (
        f"🎛 Global sozlamalar:\n\n"
        f"💰 Ovoz narxi: {format_money(price)}\n"
        f"🧾 Minimal pul yechish: {format_money(min_wd)}\n"
        f"🎮 Donat hisobi: {donat_account}"
    )


@router.callback_query(AdminMenuCB.filter(F.section == "settings"))
async def show_settings(callback: CallbackQuery, session: AsyncSession) -> None:
    await callback.message.edit_text(await _render(session), reply_markup=_settings_kb())


@router.callback_query(F.data == EDIT_PRICE_CB)
async def edit_price_prompt(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(GlobalSettingsStates.waiting_vote_price)
    await callback.message.edit_text(
        "Yangi ovoz narxini so'mda kiriting (masalan: 2000):", reply_markup=admin_kb.cancel_kb()
    )


@router.message(GlobalSettingsStates.waiting_vote_price, F.text)
async def edit_price_apply(message: Message, session: AsyncSession, state: FSMContext) -> None:
    if not message.text.strip().isdigit() or int(message.text.strip()) <= 0:
        await message.answer("❗ Musbat son kiriting:", reply_markup=admin_kb.cancel_kb())
        return
    await settings_repo.set_value(session, VOTE_PRICE, message.text.strip())
    await state.clear()
    await message.answer(await _render(session), reply_markup=_settings_kb())


@router.callback_query(F.data == EDIT_MIN_WD_CB)
async def edit_min_wd_prompt(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(GlobalSettingsStates.waiting_min_withdrawal)
    await callback.message.edit_text(
        "Yangi minimal pul yechish miqdorini so'mda kiriting:", reply_markup=admin_kb.cancel_kb()
    )


@router.message(GlobalSettingsStates.waiting_min_withdrawal, F.text)
async def edit_min_wd_apply(message: Message, session: AsyncSession, state: FSMContext) -> None:
    if not message.text.strip().isdigit() or int(message.text.strip()) <= 0:
        await message.answer("❗ Musbat son kiriting:", reply_markup=admin_kb.cancel_kb())
        return
    await settings_repo.set_value(session, MIN_WITHDRAWAL, message.text.strip())
    await state.clear()
    await message.answer(await _render(session), reply_markup=_settings_kb())


@router.callback_query(F.data == EDIT_DONAT_CB)
async def edit_donat_prompt(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(GlobalSettingsStates.waiting_donat_account)
    await callback.message.edit_text(
        "Yangi Donat hisobi ma'lumotini kiriting (masalan: o'yin ID yoki hisob raqami):",
        reply_markup=admin_kb.cancel_kb(),
    )


@router.message(GlobalSettingsStates.waiting_donat_account, F.text)
async def edit_donat_apply(message: Message, session: AsyncSession, state: FSMContext) -> None:
    text = message.text.strip()
    if not text:
        await message.answer("❗ Bo'sh bo'lishi mumkin emas. Qayta kiriting:", reply_markup=admin_kb.cancel_kb())
        return
    await settings_repo.set_value(session, DONAT_ACCOUNT, text)
    await state.clear()
    await message.answer(await _render(session), reply_markup=_settings_kb())
