"""/discovery/imports: upload a CSV of companies, map its columns, check the rows and start
research on the ones a person picks."""

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field

from app.auth.deps import AppSettings, DbSession, require_permission
from app.auth.models import User
from app.core.enums import CandidateStatus
from app.discovery import csv_import, service
from app.discovery.models import DiscoveredCompany, DiscoveryJob
from app.research.models import ResearchRun
from app.research.router import Enqueuer

router = APIRouter(prefix="/discovery/imports", tags=["discovery"])

Researcher = Annotated[User, Depends(require_permission("research.run"))]


class UploadBody(BaseModel):
    filename: str = Field(default="Upload", max_length=200)
    # The file's text. Browsers read it locally and send it as JSON; 2 MB at most.
    content: str = Field(max_length=csv_import.MAX_CHARS)


class MappingBody(BaseModel):
    mapping: dict[str, str]


class ResearchBody(BaseModel):
    row_ids: list[uuid.UUID] = Field(min_length=1, max_length=service.MAX_RESEARCH_PER_REQUEST)


class JobOut(BaseModel):
    id: uuid.UUID
    name: str
    kind: str
    status: str
    columns: list[str]
    mapping: dict[str, str]
    row_count: int
    stats: dict[str, int]
    created_by_id: uuid.UUID
    created_at: datetime

    @classmethod
    def of(cls, job: DiscoveryJob) -> "JobOut":
        return cls(
            id=job.id,
            name=job.name,
            kind=job.kind.value,
            status=job.status.value,
            columns=job.columns,
            mapping=job.mapping,
            row_count=job.row_count,
            stats=job.stats,
            created_by_id=job.created_by_id,
            created_at=job.created_at,
        )


class RowOut(BaseModel):
    id: uuid.UUID
    row_number: int
    raw: dict[str, Any]
    name: str | None
    website_url: str | None
    normalised_domain: str | None
    country: str | None
    industry: str | None
    notes: str | None
    status: str
    status_detail: str | None
    matched_account_id: uuid.UUID | None
    research_run_id: uuid.UUID | None
    run_status: str | None
    run_review_status: str | None

    @classmethod
    def of(cls, row: DiscoveredCompany, run: ResearchRun | None) -> "RowOut":
        return cls(
            id=row.id,
            row_number=row.row_number,
            raw=row.raw,
            name=row.name,
            website_url=row.website_url,
            normalised_domain=row.normalised_domain,
            country=row.country,
            industry=row.industry,
            notes=row.notes,
            status=row.status.value,
            status_detail=row.status_detail,
            matched_account_id=row.matched_account_id,
            research_run_id=row.research_run_id,
            run_status=run.status.value if run else None,
            run_review_status=run.review_status.value if run else None,
        )


class JobDetail(JobOut):
    fields: list[str]
    rows: list[RowOut]


class ResearchStarted(BaseModel):
    started: list[uuid.UUID]
    skipped: dict[str, str]
    queue_failures: int


async def _detail(
    db: DbSession, job: DiscoveryJob, row_status: CandidateStatus | None
) -> JobDetail:
    rows = await service.rows_of(db, job, row_status)
    runs = await service.run_states(db, rows)
    return JobDetail(
        **JobOut.of(job).model_dump(),
        fields=list(csv_import.FIELDS),
        rows=[
            RowOut.of(r, runs.get(r.research_run_id) if r.research_run_id else None) for r in rows
        ],
    )


@router.post("", status_code=status.HTTP_201_CREATED)
async def upload(body: UploadBody, user: Researcher, db: DbSession) -> JobDetail:
    job = await service.create_import(db, user=user, filename=body.filename, content=body.content)
    await db.commit()
    return await _detail(db, job, None)


@router.get("")
async def list_imports(
    user: Researcher, db: DbSession, limit: Annotated[int, Query(ge=1, le=100)] = 25
) -> list[JobOut]:
    return [JobOut.of(j) for j in await service.list_jobs(db, user=user, limit=limit)]


@router.get("/{job_id}")
async def get_import(
    job_id: uuid.UUID, user: Researcher, db: DbSession, status: CandidateStatus | None = None
) -> JobDetail:
    job = await service.get_job(db, user=user, job_id=job_id)
    return await _detail(db, job, status)


@router.put("/{job_id}/mapping")
async def map_and_check(
    job_id: uuid.UUID, body: MappingBody, user: Researcher, db: DbSession
) -> JobDetail:
    job = await service.get_job(db, user=user, job_id=job_id)
    await service.check(db, user=user, job=job, mapping=body.mapping)
    await db.commit()
    return await _detail(db, job, None)


@router.post("/{job_id}/research")
async def research_rows(
    job_id: uuid.UUID,
    body: ResearchBody,
    user: Researcher,
    db: DbSession,
    settings: AppSettings,
    enqueue: Enqueuer,
) -> ResearchStarted:
    job = await service.get_job(db, user=user, job_id=job_id)
    runs, skipped = await service.start_research(
        db, user=user, job=job, row_ids=body.row_ids, settings=settings
    )
    await db.commit()
    failures = await service.enqueue_all(db, runs, enqueue)
    return ResearchStarted(started=[r.id for r in runs], skipped=skipped, queue_failures=failures)
