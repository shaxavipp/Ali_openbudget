import logging

from aiogram import Bot, Router
from aiogram.exceptions import TelegramForbiddenError
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from bot.callbacks import VoteDecisionCB
from db.models.user import User
from repositories import user_repo
from services import voting_service
from services.voting_service import VoteAlreadyDecided
from utils.formatting import format_money
from utils.timezone import format_local

logger = logging.getLogger("openbudget")

router = Router(name="admin_approval")


@router.callback_query(VoteDecisionCB.filter())
async def handle_vote_decision(
    callback: CallbackQuery,
    callback_data: VoteDecisionCB,
    session: AsyncSession,
    bot: Bot,
    is_admin: bool,
) -> None:
    if not is_admin:
        await callback.answer("Ruxsat yo'q.", show_alert=True)
        return

    try:
        if callback_data.action == "approve":
            await _handle_approve(callback, session, bot, callback_data.vote_id)
        else:
            await _handle_reject(callback, session, bot, callback_data.vote_id)
    except VoteAlreadyDecided:
        await callback.answer("Bu ariza allaqachon ko'rib chiqilgan.", show_alert=True)


async def _handle_approve(
    callback: CallbackQuery, session: AsyncSession, bot: Bot, vote_id: int
) -> None:
    result = await voting_service.confirm_vote(session, vote_id)

    decided_at_str = format_local(result.vote.decided_at)
    await _close_channel_message(callback, f"✅ Tasdiqlandi — {decided_at_str}")
    await callback.answer("Tasdiqlandi.")

    await _notify_user(
        bot,
        result.user,
        f"✅ Sizning {result.vote.phone_number} raqamingiz tasdiqlandi va "
        f"hisobingizga {format_money(result.reward_amount)} qo'shildi!\n"
        "👉 Pullaringizni yechib olish uchun «💰 Hisobim» bo'limiga kiring",
    )

    if result.referral_credit is not None:
        await _notify_user(
            bot,
            result.referral_credit.referrer,
            "🎁 Sizning referalingiz birinchi ovozi tasdiqlandi!\n"
            f"Hisobingizga {format_money(result.referral_credit.bonus_amount)} bonus tushdi.",
        )


async def _handle_reject(
    callback: CallbackQuery, session: AsyncSession, bot: Bot, vote_id: int
) -> None:
    vote = await voting_service.reject_vote(session, vote_id)

    decided_at_str = format_local(vote.decided_at)
    await _close_channel_message(callback, f"❌ Rad etildi — {decided_at_str}")
    await callback.answer("Rad etildi.")

    user = await user_repo.get_by_telegram_id(session, vote.user_id)
    if user is not None:
        await _notify_user(
            bot,
            user,
            f"❌ Sizning so'rovingiz ({vote.phone_number}) bekor qilindi!",
        )


async def _close_channel_message(callback: CallbackQuery, status_line: str) -> None:
    message = callback.message
    if message is None:
        return
    new_text = f"{message.text or ''}\n\n{status_line}"
    await message.edit_text(new_text, reply_markup=None)


async def _notify_user(bot: Bot, user: User, text: str) -> None:
    try:
        await bot.send_message(user.telegram_id, text)
    except TelegramForbiddenError:
        user.is_blocked = True
        logger.info("User %s blocked the bot, could not deliver notification", user.telegram_id)
