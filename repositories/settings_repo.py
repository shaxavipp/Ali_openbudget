from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.settings import VOTE_COUNTER, GlobalSetting

DEFAULTS = {
    "vote_price": "2000",
    "min_withdrawal": "300000",
    "referral_bonus": "5000",
    "referral_promo_text": (
        "Do'stlaringizni taklif qiling! Ular ovoz berib tasdiqlansa, sizga bonus tushadi."
    ),
    "donat_account": "Hali sozlanmagan",
    VOTE_COUNTER: "1",
}


async def get_all(session: AsyncSession) -> dict[str, str]:
    result = await session.execute(select(GlobalSetting))
    return {row.key: row.value for row in result.scalars().all()}


async def get(session: AsyncSession, key: str) -> str | None:
    setting = await session.get(GlobalSetting, key)
    return setting.value if setting else None


async def set_value(session: AsyncSession, key: str, value: str) -> None:
    setting = await session.get(GlobalSetting, key)
    if setting is None:
        session.add(GlobalSetting(key=key, value=value))
    else:
        setting.value = value
    await session.flush()


async def seed_defaults(session: AsyncSession) -> None:
    existing = await get_all(session)
    for key, value in DEFAULTS.items():
        if key not in existing:
            session.add(GlobalSetting(key=key, value=value))
    await session.commit()


async def get_and_increment_vote_counter(session: AsyncSession) -> int:
    """Returns the current vote counter value, then bumps it by 1 for next time.

    Row-locked (SELECT ... FOR UPDATE) so two votes finalizing at the same
    moment can't both read the same number — each caller blocks until the
    previous one commits its increment, guaranteeing every vote gets a
    unique, strictly increasing number even under concurrent submissions.
    """
    stmt = select(GlobalSetting).where(GlobalSetting.key == VOTE_COUNTER).with_for_update()
    result = await session.execute(stmt)
    setting = result.scalar_one_or_none()

    if setting is None:
        session.add(GlobalSetting(key=VOTE_COUNTER, value="2"))
        await session.flush()
        return 1

    current = int(setting.value)
    setting.value = str(current + 1)
    await session.flush()
    return current
