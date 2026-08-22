from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.settings import GlobalSetting

DEFAULTS = {
    "vote_price": "2000",
    "min_withdrawal": "300000",
    "referral_bonus": "5000",
    "referral_promo_text": (
        "Do'stlaringizni taklif qiling! Ular ovoz berib tasdiqlansa, sizga bonus tushadi."
    ),
    "donat_account": "Hali sozlanmagan",
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
