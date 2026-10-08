"""Research run API models."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.core.enums import JobStatus
from app.evidence.models import Observation as ObservationRow
from app.research.models import ResearchPage, ResearchRun, ResearchStage


class StartRun(BaseModel):
    url: str = Field(min_length=1, max_length=2000)


class StageOut(BaseModel):
    stage: str
    status: str
    progress_pct: int
    started_at: datetime | None
    finished_at: datetime | None
    error: str | None
    detail: dict[str, Any]

    @classmethod
    def of(cls, stage: ResearchStage) -> "StageOut":
        return cls(
            stage=stage.stage.value,
            status=stage.status.value,
            progress_pct=stage.progress_pct,
            started_at=stage.started_at,
            finished_at=stage.finished_at,
            error=stage.error,
            detail=stage.detail,
        )


class PageOut(BaseModel):
    kind: str
    url: str
    final_url: str | None
    discovered_via: str
    category: str | None
    status_code: int | None
    content_type: str | None
    bytes: int
    from_cache: bool
    rendered: bool
    title: str | None
    canonical_url: str | None
    duplicate_of_url: str | None
    skip_reason: str | None
    error: str | None

    @classmethod
    def of(cls, page: ResearchPage) -> "PageOut":
        return cls.model_validate(
            {
                **{f: getattr(page, f) for f in cls.model_fields if f != "kind"},
                "kind": page.kind.value,
            }
        )


class RunOut(BaseModel):
    id: uuid.UUID
    input_url: str
    normalised_domain: str
    status: str
    review_status: str
    requested_by_id: uuid.UUID
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    error: str | None
    retry_count: int
    possible_duplicate_of: list[str]
    # Overall progress across the stages this run has.
    progress_pct: int
    stages: list[StageOut]

    @classmethod
    def of(cls, run: ResearchRun, stages: list[ResearchStage]) -> "RunOut":
        if run.status == JobStatus.COMPLETED:
            progress = 100
        else:
            progress = int(sum(s.progress_pct for s in stages) / len(stages)) if stages else 0
        return cls(
            id=run.id,
            input_url=run.input_url,
            normalised_domain=run.normalised_domain,
            status=run.status.value,
            review_status=run.review_status.value,
            requested_by_id=run.requested_by_id,
            created_at=run.created_at,
            started_at=run.started_at,
            finished_at=run.finished_at,
            error=run.error,
            retry_count=run.retry_count,
            possible_duplicate_of=run.possible_duplicate_of,
            progress_pct=progress,
            stages=[StageOut.of(s) for s in stages],
        )


class RunDetail(RunOut):
    pages: list[PageOut]


class EvidenceOut(BaseModel):
    id: uuid.UUID
    source_url: str
    evidence_type: str
    excerpt: str
    collected_at: datetime
    confidence: float


class ObservationOut(BaseModel):
    id: uuid.UUID
    area: str
    key: str
    value: Any
    confidence: float
    seen_on: list[str]
    evidence: EvidenceOut

    @classmethod
    def of(cls, row: "ObservationRow") -> "ObservationOut":
        ev = row.evidence
        return cls(
            id=row.id,
            area=row.area.value,
            key=row.key,
            value=row.value,
            confidence=float(row.confidence),
            seen_on=row.seen_on,
            evidence=EvidenceOut(
                id=ev.id,
                source_url=ev.source_url,
                evidence_type=ev.evidence_type.value,
                excerpt=ev.evidence_text,
                collected_at=ev.collected_at,
                confidence=float(ev.confidence),
            ),
        )


class Intelligence(BaseModel):
    """Everything extracted for a run's latest attempt, grouped by area."""

    run_id: uuid.UUID
    attempt: int
    areas: dict[str, list[ObservationOut]]
