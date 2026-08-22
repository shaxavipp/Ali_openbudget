import asyncio
import logging
import os

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.callbacks import AdminCancelCB, AdminMenuCB
from bot.filters import IsAdmin
from bot.keyboards import admin_kb

logger = logging.getLogger("openbudget")

router = Router(name="admin_menu")
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())


@router.message(Command("admin"))
async def open_admin_panel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(admin_kb.PANEL_TITLE, reply_markup=admin_kb.admin_root_kb())


@router.callback_query(AdminMenuCB.filter(F.section == "root"))
async def show_root(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text(admin_kb.PANEL_TITLE, reply_markup=admin_kb.admin_root_kb())


@router.callback_query(AdminCancelCB.filter())
async def cancel_flow(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text(admin_kb.PANEL_TITLE, reply_markup=admin_kb.admin_root_kb())


@router.callback_query(AdminMenuCB.filter(F.section == "restart"))
async def confirm_restart(callback: CallbackQuery) -> None:
    await callback.message.edit_text(
        "⚠️ Botni qayta ishga tushirmoqchimisiz?\n\n"
        "Bot bir necha soniyaga javob bermay qoladi, so'ng avtomatik qayta ishga tushadi.",
        reply_markup=admin_kb.restart_confirm_kb(),
    )
    await callback.answer()


@router.callback_query(AdminMenuCB.filter(F.section == "restart_confirm"))
async def do_restart(callback: CallbackQuery) -> None:
    logger.warning("Admin (id=%s) botni qayta ishga tushirishni so'radi", callback.from_user.id)
    await callback.message.edit_text("🔄 Bot qayta ishga tushirilmoqda, biroz kuting...")
    await callback.answer()
    # Give Telegram a moment to actually deliver the edited message before the
    # process exits — Railway's restart policy is what brings it back up.
    asyncio.create_task(_exit_after_delay())


async def _exit_after_delay() -> None:
    await asyncio.sleep(1.5)
    os._exit(0)
