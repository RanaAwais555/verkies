"""Watching accounts and what monitoring found (master context §15; slices 6.1 to 6.3)."""

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, CreatedMixin, IdMixin, TimestampMixin


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
    reviewed_at: Mapped[datetime | None]
    reviewed_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    # A website change (slice 6.2): what changed, with the text before and after.
    detail: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    # Alert rules (slice 6.3): the flag raised (opportunity_detected or requires_review), the
    # rules that matched ({id, name, action}) and the follow-up task one of them created.
    raised: Mapped[str | None] = mapped_column(String(30))
    rules: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list, server_default="[]")
    task_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("tasks.id"))


class AlertRule(IdMixin, TimestampMixin, Base):
    """What to do when monitoring finds something (slice 6.3). A rule matches an alert by its
    kind, its signal and, for a website change, its topic; an empty list matches anything. Its
    action raises a flag on the alert or creates a follow-up task for the account's owner."""

    __tablename__ = "alert_rules"

    name: Mapped[str] = mapped_column(String(120))
    active: Mapped[bool] = mapped_column(default=True)
    kinds: Mapped[list[str]] = mapped_column(JSONB, default=list)  # job_posting, website, ...
    signals: Mapped[list[str]] = mapped_column(JSONB, default=list)  # funding, new_leader, ...
    topics: Mapped[list[str]] = mapped_column(JSONB, default=list)  # services, pricing, ...
    action: Mapped[str] = mapped_column(String(30))  # opportunity_detected, requires_review, task
    task_title: Mapped[str | None] = mapped_column(String(200))
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
