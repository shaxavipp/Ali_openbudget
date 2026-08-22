from decimal import Decimal

from sqlalchemy import String, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.user import User
from db.models.vote import Vote, VoteStatus


async def create_vote(
    session: AsyncSession,
    user_id: int,
    project_id: int,
    phone_number: str,
    screenshot_file_ids: list[str],
    reward_amount: Decimal,
) -> Vote:
    vote = Vote(
        user_id=user_id,
        project_id=project_id,
        phone_number=phone_number,
        screenshot_file_ids=screenshot_file_ids,
        reward_amount=reward_amount,
    )
    session.add(vote)
    await session.flush()
    return vote


async def set_admin_message(session: AsyncSession, vote: Vote, message_id: int, chat_id: int) -> None:
    vote.admin_message_id = message_id
    vote.admin_channel_chat_id = chat_id
    await session.flush()


async def get_active_by_phone(session: AsyncSession, phone_number: str) -> Vote | None:
    """A phone number with a pending or already-confirmed vote can't submit again.

    Only if every prior vote for this number was rejected is it free to retry.
    """
    stmt = (
        select(Vote)
        .where(
            Vote.phone_number == phone_number,
            Vote.status.in_((VoteStatus.PENDING, VoteStatus.CONFIRMED)),
        )
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_pending_for_update(session: AsyncSession, vote_id: int) -> Vote | None:
    stmt = (
        select(Vote)
        .where(Vote.id == vote_id, Vote.status == VoteStatus.PENDING)
        .with_for_update()
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def list_paginated(session: AsyncSession, offset: int, limit: int) -> list[Vote]:
    stmt = select(Vote).order_by(Vote.created_at.desc()).offset(offset).limit(limit)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def count_all(session: AsyncSession) -> int:
    result = await session.execute(select(func.count()).select_from(Vote))
    return result.scalar() or 0


async def count_by_status(session: AsyncSession, status: VoteStatus) -> int:
    stmt = select(func.count()).select_from(Vote).where(Vote.status == status)
    result = await session.execute(stmt)
    return result.scalar() or 0


async def top_voters(session: AsyncSession, limit: int = 10) -> list[tuple[str, int]]:
    """Top users by confirmed vote count, as (display_name, vote_count) pairs.

    display_name prefers the Telegram username, then full name, then falls
    back to the numeric telegram_id so nobody renders as a blank line.
    """
    name_col = func.coalesce(User.username, User.full_name, cast(User.telegram_id, String)).label(
        "name"
    )
    stmt = (
        select(name_col, func.count(Vote.id).label("cnt"))
        .join(User, User.telegram_id == Vote.user_id)
        .where(Vote.status == VoteStatus.CONFIRMED)
        .group_by(User.telegram_id, User.username, User.full_name)
        .order_by(func.count(Vote.id).desc())
        .limit(limit)
    )
    result = await session.execute(stmt)
    return [(row.name, row.cnt) for row in result.all()]


async def list_by_user_paginated(
    session: AsyncSession,
    user_id: int,
    status: VoteStatus | None,
    offset: int,
    limit: int,
) -> list[Vote]:
    stmt = select(Vote).where(Vote.user_id == user_id)
    if status is not None:
        stmt = stmt.where(Vote.status == status)
    stmt = stmt.order_by(Vote.created_at.desc()).offset(offset).limit(limit)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def count_by_user(session: AsyncSession, user_id: int, status: VoteStatus | None) -> int:
    stmt = select(func.count()).select_from(Vote).where(Vote.user_id == user_id)
    if status is not None:
        stmt = stmt.where(Vote.status == status)
    result = await session.execute(stmt)
    return result.scalar() or 0
