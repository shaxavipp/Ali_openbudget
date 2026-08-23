from aiogram import F, Router
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.user_kb import GUIDE_BUTTON, PAYMENTS_BUTTON, RATING_BUTTON
from db.models.vote import VoteStatus
from repositories import vote_repo

router = Router(name="user_info")

# Kanal — "bizning bot orqali to'langan barcha to'lovlar isbot kanali"
PAYMENTS_CHANNEL_URL = "h"
ADMIN_USERNAME = "@nvr_ali"

RATING_REFRESH_CB = "info:rating_refresh"

GUIDE_TEXT = (
    "❓ <b>Bot nima qila oladi?</b>:\n"
    "— Botimiz orqali OpenBudget uchun ovoz berib pul ishlashingiz mumkin. "
    "To'plangan pullarni telefon raqamingizga paynet tariqasida yoki karta "
    "raqamingizga yechib olishingiz mumkin.\n\n"
    "❓ <b>Pulni qanday yechib olaman?</b>:\n"
    "— 💵 Hisobim bo'limiga o'ting va «💰 Pul yechish» tugmasini bosing. "
    "To'lov tizimlaridan birini tanlang. Karta raqamingiz yoki telefon "
    "raqamingizni kiriting. Administratorimiz hisobingizni to'ldiradi."
)


@router.message(F.text == PAYMENTS_BUTTON)
async def payments_channel(message: Message) -> None:
    await message.answer(
        "🎯 Bizning bot orqali to'langan barcha to'lovlar isbot kanali:",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="✅ Kanalga o'tish", url=PAYMENTS_CHANNEL_URL)]
            ]
        ),
    )


async def _build_rating_text(session: AsyncSession) -> str:
    confirmed = await vote_repo.count_by_status(session, VoteStatus.CONFIRMED)
    rejected = await vote_repo.count_by_status(session, VoteStatus.REJECTED)
    top = await vote_repo.top_voters(session, limit=10)

    medals = {0: "🥇", 1: "🥈", 2: "🥉"}
    if top:
        lines = [
            f"{medals.get(i, f'{i + 1}.')} {name} — <b>{cnt} ta ovoz</b>"
            for i, (name, cnt) in enumerate(top)
        ]
        rating_block = "\n".join(lines)
    else:
        rating_block = "Hozircha tasdiqlangan ovozlar yo'q."

    return (
        "🏆 <b>Umumiy Top reyting</b>\n\n"
        f"{rating_block}\n\n"
        f"🎯 Tasdiqlangan ovozlar: {confirmed} ta\n"
        f"♻️ Bekor qilingan ovozlar: {rejected} ta\n"
        f"🙆‍♂️ Bizning admin: {ADMIN_USERNAME}"
    )


def _rating_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Reytingni yangilash", callback_data=RATING_REFRESH_CB)]
        ]
    )


@router.message(F.text == RATING_BUTTON)
async def show_rating(message: Message, session: AsyncSession) -> None:
    text = await _build_rating_text(session)
    await message.answer(text, reply_markup=_rating_kb())


@router.callback_query(F.data == RATING_REFRESH_CB)
async def refresh_rating(callback: CallbackQuery, session: AsyncSession) -> None:
    text = await _build_rating_text(session)
    try:
        await callback.message.edit_text(text, reply_markup=_rating_kb())
    except Exception:
        # matn o'zgarmagan bo'lsa Telegram "message is not modified" xatosi beradi —
        # bu zararsiz, foydalanuvchiga faqat "yangilandi" degan signal yetsa yetarli
        pass
    await callback.answer("Yangilandi")


@router.message(F.text == GUIDE_BUTTON)
async def show_guide(message: Message) -> None:
    await message.answer(GUIDE_TEXT)
