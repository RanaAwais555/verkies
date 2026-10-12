"""In-app notifications (master context §13 Notifications; slice 6.3)."""

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, CreatedMixin, IdMixin


class Notification(IdMixin, CreatedMixin, Base):
    """Something a person should know about, shown in the app. Nothing is sent anywhere."""

    __tablename__ = "notifications"
    __table_args__ = (
        Index(
            "ix_notifications_user_unread",
            "user_id",
            "created_at",
            postgresql_where=text("read_at IS NULL"),
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(40))  # monitoring_alert, rule_task
    title: Mapped[str] = mapped_column(String(300))
    body: Mapped[str | None] = mapped_column(Text)
    account_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("accounts.id"))
    link: Mapped[str | None] = mapped_column(String(300))  # an app path, e.g. /accounts/<id>
    read_at: Mapped[datetime | None]
