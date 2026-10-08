"""Review queue and approval API models."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.core.enums import RejectionReason


class DuplicateOut(BaseModel):
    account_id: uuid.UUID
    name: str
    primary_domain: str | None
    match: str
    similarity: float | None = None


class QueueItemOut(BaseModel):
    run_id: uuid.UUID
    domain: str
    input_url: str
    company: str | None
    priority_score: float | None
    priority_band: str | None
    qualifies: bool
    hard_reject: bool
    recommended_rejection: str | None
    explanation: str
    next_action: str | None
    scores: dict[str, float | None]
    possible_duplicates: list[DuplicateOut]
    requested_by_id: uuid.UUID
    finished_at: datetime | None


class ApproveBody(BaseModel):
    owner_id: uuid.UUID | None = None
    due_at: datetime | None = None
    task_title: str | None = Field(default=None, min_length=1, max_length=200)
    # Attach to this existing account instead of creating one (a possible duplicate).
    account_id: uuid.UUID | None = None
    # Confirms the prospect is a new company although similar accounts exist.
    create_new_account: bool = False
    # Required when approving against the engines (hard reject or below threshold).
    override_reason: str | None = Field(default=None, max_length=2000)


class ApprovalOut(BaseModel):
    run_id: uuid.UUID
    account_id: uuid.UUID
    created_account: bool
    lead_id: uuid.UUID
    opportunity_id: uuid.UUID | None
    task_id: uuid.UUID
    task_due_at: datetime | None
    contact_ids: list[uuid.UUID]


class RejectBody(BaseModel):
    reason: RejectionReason
    note: str | None = Field(default=None, max_length=2000)
    # Also add the domain to the suppression list, so it is never re-added.
    suppress: bool = False


class RejectionOut(BaseModel):
    run_id: uuid.UUID
    review_status: str
    rejection_reason: str
    rejection_note: str | None
    suppressed: bool


def scores_of(summary: dict[str, Any]) -> dict[str, float | None]:
    keys = ("icp_score", "opportunity_score", "intent_score", "buyer_confidence", "data_confidence")
    return {k: summary.get(k) for k in keys}
