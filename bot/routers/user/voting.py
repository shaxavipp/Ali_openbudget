import asyncio
import logging
from decimal import Decimal

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    Message,
)
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards import user_kb
from bot.keyboards.approval_kb import vote_decision_kb
from bot.keyboards.user_kb import VOTE_BUTTON, main_menu
from bot.states.voting_states import VotingStates
from config import settings
from db.base import async_session_factory
from db.models.settings import VOTE_PRICE
from db.models.user import User
from db.models.vote import VoteStatus
from repositories import project_repo, settings_repo, vote_repo
from services import voting_service
from utils.formatting import format_money
from utils.phone import normalize_uz_phone
from utils.timezone import format_local

logger = logging.getLogger("openbudget")

router = Router(name="user_voting")

VOTE_DONE_CB = "voting:vote_done"

# A Telegram album (media group) arrives as several separate messages in quick
# succession with no explicit "end of album" signal. We debounce: each new album
# part reschedules the finalize timer, so it only fires once the album has stopped
# growing. A lone (non-grouped) photo has no media_group_id and finalizes instantly.
ALBUM_DEBOUNCE_SECONDS = 1.5

_locks: dict[int, asyncio.Lock] = {}
_pending_finalize: dict[int, asyncio.Task] = {}


def _get_lock(user_id: int) -> asyncio.Lock:
    lock = _locks.get(user_id)
    if lock is None:
        lock = asyncio.Lock()
        _locks[user_id] = lock
    return lock


@router.message(F.text == VOTE_BUTTON)
async def start_voting(message: Message, session: AsyncSession, state: FSMContext) -> None:
    project = await project_repo.get_active_project(session)
    if project is None:
        await message.answer("Hozircha faol loyiha yo'q. Birozdan so'ng qayta urinib ko'ring.")
        return

    price_raw = await settings_repo.get(session, VOTE_PRICE)
    price = Decimal(price_raw) if price_raw else Decimal("0")

    await state.update_data(project_id=project.id)
    await state.set_state(VotingStates.waiting_phone)
    await message.answer(
        f"💰 Ovoz berib tasdiqlansa, hisobingizga <b>{format_money(price)}</b> tushadi.\n\n"
        "📞 Telefon raqamingizni kiriting:\n<code>+998901234567</code>",
        reply_markup=user_kb.cancel_only_menu(),
    )


@router.message(F.text == user_kb.CANCEL_BUTTON)
async def cancel_voting(message: Message, state: FSMContext) -> None:
    current_state = await state.get_state()
    if current_state not in {
        VotingStates.waiting_phone,
        VotingStates.waiting_vote_confirm,
        VotingStates.waiting_screenshot,
    }:
        return

    pending_task = _pending_finalize.pop(message.from_user.id, None)
    if pending_task is not None:
        pending_task.cancel()

    await state.clear()
    await message.answer("Bekor qilindi.", reply_markup=main_menu())


@router.message(VotingStates.waiting_phone, F.text, ~F.text.in_(user_kb.MENU_BUTTON_TEXTS))
async def phone_from_text(message: Message, session: AsyncSession, state: FSMContext) -> None:
    phone = normalize_uz_phone(message.text)
    if phone is None:
        await message.answer(
            "❗ Telefon raqami noto'g'ri. Namuna: +998901234567. Qayta kiriting:"
        )
        return

    existing = await vote_repo.get_active_by_phone(session, phone)
    if existing is not None:
        status_text = (
            "allaqachon tasdiqlangan" if existing.status == VoteStatus.CONFIRMED else "ko'rib chiqilmoqda"
        )
        await message.answer(
            f"❗ Bu raqam ({phone}) uchun so'rov {status_text}. "
            "Bitta raqamdan faqat bitta faol so'rov yuborish mumkin. Boshqa raqam kiriting:"
        )
        return

    data = await state.get_data()
    project = await project_repo.get_by_id(session, data["project_id"])
    if project is None or not project.is_active:
        await state.clear()
        await message.answer(
            "Kechirasiz, bu loyiha uchun ovoz yig'ish yakunlandi. Qaytadan urinib ko'ring.",
            reply_markup=main_menu(),
        )
        return

    await state.update_data(phone_number=phone)
    await state.set_state(VotingStates.waiting_vote_confirm)
    await message.answer(
        "✅ Raqam qabul qilindi.\n\n"
        "🔗 Pastdagi havola orqali ovoz bering, so'ng \"Ovoz berdim\" tugmasini bosing:",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🔗 Ovoz berish", url=project.board_url)],
                [InlineKeyboardButton(text="✅ Ovoz berdim", callback_data=VOTE_DONE_CB)],
            ]
        ),
    )


@router.callback_query(VotingStates.waiting_vote_confirm, F.data == VOTE_DONE_CB)
async def vote_done(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(screenshot_ids=[], screenshot_message_ids=[])
    await state.set_state(VotingStates.waiting_screenshot)
    await callback.message.answer(
        "📮 Ovoz berganingiz uchun rahmat!\n\n"
        "📱 Endi ovoz berganingizni tasdiqlovchi skrinshotni yuboring."
    )


@router.message(VotingStates.waiting_screenshot, F.photo)
async def screenshot_added(
    message: Message,
    session: AsyncSession,
    state: FSMContext,
    db_user: User,
    bot: Bot,
) -> None:
    user_id = db_user.telegram_id
    async with _get_lock(user_id):
        data = await state.get_data()
        screenshot_ids: list[str] = data.get("screenshot_ids", [])
        screenshot_message_ids: list[int] = data.get("screenshot_message_ids", [])
        screenshot_ids.append(message.photo[-1].file_id)
        screenshot_message_ids.append(message.message_id)
        await state.update_data(
            screenshot_ids=screenshot_ids, screenshot_message_ids=screenshot_message_ids
        )

        if message.media_group_id is None:
            # a lone photo — no siblings to wait for, finalize immediately
            existing_task = _pending_finalize.pop(user_id, None)
            if existing_task is not None:
                existing_task.cancel()
            await _finalize_and_handle_errors(session, state, bot, db_user, own_session=False)
            return

        # part of an album — more parts may still be arriving; (re)schedule the debounce
        existing_task = _pending_finalize.pop(user_id, None)
        if existing_task is not None:
            existing_task.cancel()
        _pending_finalize[user_id] = asyncio.create_task(
            _finalize_after_delay(user_id, state, bot, db_user)
        )


async def _finalize_after_delay(user_id: int, state: FSMContext, bot: Bot, db_user: User) -> None:
    try:
        await asyncio.sleep(ALBUM_DEBOUNCE_SECONDS)
    except asyncio.CancelledError:
        return

    async with _get_lock(user_id):
        _pending_finalize.pop(user_id, None)
        async with async_session_factory() as session:
            await _finalize_and_handle_errors(session, state, bot, db_user, own_session=True)


async def _finalize_and_handle_errors(
    session: AsyncSession, state: FSMContext, bot: Bot, db_user: User, *, own_session: bool
) -> None:
    """Runs the finalize step and guarantees the user gets *some* response.

    Without this, a failure partway through (e.g. a transient Telegram API error while
    forwarding/posting) would either silently vanish (background album task) or leave a
    half-submitted vote row committed with nothing posted to the channel. On any failure
    we roll back so the vote is never left in that orphaned state, and the user's phone
    number stays free to retry.
    """
    try:
        await _finalize_submission(session, state, bot, db_user)
        if own_session:
            await session.commit()
    except Exception:
        logger.exception("Ovoz arizasini yakunlashda xatolik (user_id=%s)", db_user.telegram_id)
        await session.rollback()
        await state.clear()
        try:
            await bot.send_message(
                db_user.telegram_id,
                "⚠️ Arizangizni yuborishda xatolik yuz berdi. "
                "Iltimos, \"📮 Ovoz berish\" orqali qaytadan urinib ko'ring.",
                reply_markup=main_menu(),
            )
        except Exception:  # noqa: BLE001 - best-effort notification only
            pass


async def _finalize_submission(
    session: AsyncSession, state: FSMContext, bot: Bot, db_user: User
) -> None:
    data = await state.get_data()
    screenshot_ids: list[str] = data.get("screenshot_ids") or []
    screenshot_message_ids: list[int] = data.get("screenshot_message_ids") or []
    project_id = data.get("project_id")
    phone_number = data.get("phone_number")
    if not screenshot_ids or project_id is None or phone_number is None:
        # nothing to finalize — a stray/duplicate call after the flow already completed
        return

    # forward_messages requires strictly increasing message ids; concurrent task
    # scheduling doesn't guarantee photos are appended in arrival order, so sort them
    # (message_id is monotonically increasing per chat, so this is always correct)
    screenshot_message_ids, screenshot_ids = (
        list(seq) for seq in zip(*sorted(zip(screenshot_message_ids, screenshot_ids)))
    )

    project = await project_repo.get_active_project(session)
    if project is None or project.id != project_id:
        await state.clear()
        await bot.send_message(
            db_user.telegram_id,
            "Kechirasiz, bu loyiha uchun ovoz yig'ish yakunlandi. Qaytadan urinib ko'ring.",
            reply_markup=main_menu(),
        )
        return

    vote = await voting_service.submit_vote(
        session, db_user, project, phone_number, screenshot_ids
    )
    await session.flush()

    # forward the user's own screenshot message(s) to the channel as-is, instead of
    # re-uploading copies — keeps Telegram's "forwarded from" attribution as proof of origin
    if len(screenshot_message_ids) == 1:
        await bot.forward_message(
            chat_id=settings.channel_id,
            from_chat_id=db_user.telegram_id,
            message_id=screenshot_message_ids[0],
        )
    else:
        await bot.forward_messages(
            chat_id=settings.channel_id,
            from_chat_id=db_user.telegram_id,
            message_ids=screenshot_message_ids,
        )

    caption = (
        "🗳 Yangi ovoz tasdiqlash so'rovi\n\n"
        f"👤 Foydalanuvchi: {db_user.full_name or '—'} "
        f"(@{db_user.username or '—'}, ID: {db_user.telegram_id})\n"
        f"📞 Telefon: {phone_number}\n"
        f"📌 Loyiha: {project.name}\n"
        f"💰 Mukofot: {format_money(vote.reward_amount)}\n"
        f"🕒 Vaqt: {format_local(vote.created_at)}"
    )
    sent = await bot.send_message(
        chat_id=settings.channel_id,
        text=caption,
        reply_markup=vote_decision_kb(vote.id),
    )
    await vote_repo.set_admin_message(session, vote, sent.message_id, sent.chat.id)

    # Tekshiruvchilar kanali: faqat skrinshot(lar) + telefon raqami va sana, tugmasiz.
    # settings'da verifiers_channel_id bo'lmasa yoki bo'sh bo'lsa, jimgina o'tkazib
    # yuboriladi — bu blok admin kanaliga yuborishga hech qanday ta'sir qilmaydi.
    verifiers_channel_id = getattr(settings, "verifiers_channel_id", None)
    if verifiers_channel_id:
        try:
            verifier_caption = (
                f"📞 {phone_number}\n"
                f"🕒 {format_local(vote.created_at)}"
            )
            if len(screenshot_ids) == 1:
                await bot.send_photo(
                    chat_id=verifiers_channel_id,
                    photo=screenshot_ids[0],
                    caption=verifier_caption,
                )
            else:
                media = [
                    InputMediaPhoto(
                        media=fid,
                        caption=verifier_caption if index == 0 else None,
                    )
                    for index, fid in enumerate(screenshot_ids)
                ]
                await bot.send_media_group(chat_id=verifiers_channel_id, media=media)
        except Exception:
            # tekshiruvchilar kanaliga yuborish muvaffaqiyatsiz bo'lsa ham, asosiy
            # oqim (admin tasdiqlash) buzilmasligi kerak — shuning uchun faqat log
            logger.exception(
                "Tekshiruvchilar kanaliga yuborishda xatolik (vote_id=%s)", vote.id
            )

    await state.clear()
    await bot.send_message(
        db_user.telegram_id,
        "✅ Ovoz so'rovingiz qabul qilindi va tekshiruvga yuborildi!\n\n"
        "⏳ So'rovingiz admin tomonidan ko'rib chiqiladi. Natija haqida xabar olasiz.",
        reply_markup=main_menu(),
    )


@router.message(VotingStates.waiting_screenshot, ~F.text.in_(user_kb.MENU_BUTTON_TEXTS))
async def screenshot_missing(message: Message) -> None:
    await message.answer("📸 Iltimos, skrinshot rasmini yuboring.")
