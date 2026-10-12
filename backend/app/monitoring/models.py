"""Watching accounts and what monitoring found (master context §15 Monitoring; slices 6.1, 6.2)."""

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, CreatedMixin, IdMixin


class Watch(IdMixin, CreatedMixin, Base):
    """A person watching an account: VROS re-checks it and tells them what changed."""

    __tablename__ = "watches"
    __table_args__ = (UniqueConstraint("account_id", "user_id"),)

    account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("accounts.id"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)


class MonitorAlert(IdMixin, CreatedMixin, Base):
    """Something new a monitoring check found on a watched account, with its evidence."""

    __tablename__ = "monitor_alerts"

    account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("accounts.id"), index=True)
    # The monitoring check (a research run of kind "monitor") and the observation it recorded.
    research_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("research_runs.id"))
    observation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("observations.id"))
    kind: Mapped[str] = mapped_column(String(60))  # job_posting, news, registry, website
    signal: Mapped[str | None] = mapped_column(String(60))  # e.g. developer_hiring, funding
    title: Mapped[str] = mapped_column(Text)
    source_url: Mapped[str] = mapped_column(Text)
    happened_on: Mapped[date | None]
    # A website change (slice 6.2): what changed, with the text before and after.
    detail: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    reviewed_at: Mapped[datetime | None]
    reviewed_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
