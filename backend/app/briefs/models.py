"""The lead brief for a research run (§11). Each section stores the claim IDs it shows."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import ForeignKey, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import BriefMode
from app.core.models import Base, IdMixin, text_enum


class LeadBrief(IdMixin, Base):
    __tablename__ = "lead_briefs"

    research_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("research_runs.id", ondelete="CASCADE"), unique=True
    )
    account_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("accounts.id"), index=True)
    # {"why_verkies": {"text": ..., "claim_ids": [...]}, "why_now": {...}, ...}
    sections: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    mode: Mapped[BriefMode] = mapped_column(text_enum(BriefMode))
    # Provider, model, prompt version and parameters, for reproduction and audit.
    generated_by: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    generated_at: Mapped[datetime] = mapped_column(server_default=func.now())
