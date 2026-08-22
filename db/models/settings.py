from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base

VOTE_PRICE = "vote_price"
MIN_WITHDRAWAL = "min_withdrawal"
REFERRAL_BONUS = "referral_bonus"
REFERRAL_PROMO_TEXT = "referral_promo_text"
DONAT_ACCOUNT = "donat_account"


class GlobalSetting(Base):
    __tablename__ = "global_settings"

    key: Mapped[str] = mapped_column(primary_key=True)
    value: Mapped[str]
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
