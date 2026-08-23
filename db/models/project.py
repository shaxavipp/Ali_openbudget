from datetime import datetime

from sqlalchemy import DateTime, Index, func, text
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class Project(Base):
    __tablename__ = "projects"
    __table_args__ = (
        Index(
            "one_active_project",
            "is_active",
            unique=True,
            postgresql_where=text("is_active = true"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    board_url: Mapped[str]
    bot_url: Mapped[str | None] = mapped_column(default=None)  # Telegram bot havolasi (t.me/...)
    queue_order: Mapped[int]
    target_votes: Mapped[int | None] = mapped_column(default=None)  # NULL = cheksiz
    is_active: Mapped[bool] = mapped_column(default=False)
    is_deleted: Mapped[bool] = mapped_column(default=False)
    confirmed_votes_count: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
