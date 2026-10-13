"""/registers (slice 8.1): the regulators' registers VROS keeps, how each last refreshed, a
refresh on demand for admins, and searching one to start a discovery job."""

from collections.abc import Callable
from datetime import date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field

from app.auth.deps import AppSettings, DbSession, require_permission
from app.auth.models import User
from app.core.errors import AppError, NotFound
from app.discovery import service as discovery
from app.discovery.router import JobDetail, _detail
from app.registers import search
from app.registers.models import RegisterSource
from app.registers.refresh import SOURCES
from app.registers.sources import LONDON_AREAS
from app.research.router import QueueUnavailable

router = APIRouter(prefix="/registers", tags=["registers"])
search_router = APIRouter(prefix="/discovery/register-searches", tags=["discovery"])

Reader = Annotated[User, Depends(require_permission("research.run", "config.manage"))]
Researcher = Annotated[User, Depends(require_permission("research.run"))]
Admin = Annotated[User, Depends(require_permission("config.manage"))]


class RegisterNotLoaded(AppError):
    status_code = 409
    code = "register_not_loaded"


class SourceOut(BaseModel):
    key: str
    name: str
    publisher: str
    attribution: str
    cadence_hours: int
    configured: bool
    last_checked_at: datetime | None
    last_changed_at: datetime | None
    last_status: str | None
    last_error: str | None
    record_count: int
    active_count: int
    detail: dict[str, int]


@router.get("/sources")
async def sources(_: Reader, db: DbSession, settings: AppSettings) -> list[SourceOut]:
    out = []
    for key, source in SOURCES.items():
        row = await db.get(RegisterSource, key)
        out.append(
            SourceOut(
                key=key,
                name=source.name,
                publisher=source.publisher,
                attribution=source.attribution,
                cadence_hours=source.cadence_hours,
                configured=source.configured(settings),
                last_checked_at=row.last_checked_at if row else None,
                last_changed_at=row.last_changed_at if row else None,
                last_status=row.last_status.value if row and row.last_status else None,
                last_error=row.last_error if row else None,
                record_count=row.record_count if row else 0,
                active_count=row.active_count if row else 0,
                detail=row.detail if row else {},
            )
        )
    return out


def enqueue_refresh(key: str) -> None:
    from app.workers.celery_app import celery_app

    celery_app.send_task("vros.registers.refresh", args=[key])


def get_refresh_enqueuer() -> Callable[[str], None]:
    return enqueue_refresh


class RefreshQueued(BaseModel):
    key: str
    queued: bool


@router.post("/sources/{key}/refresh", status_code=status.HTTP_202_ACCEPTED)
async def refresh_now(
    key: str,
    _: Admin,
    enqueue: Annotated[Callable[[str], None], Depends(get_refresh_enqueuer)],
) -> RefreshQueued:
    """Refresh one source now instead of waiting for the worker's schedule."""
    if key not in SOURCES:
        raise NotFound("No such register.")
    try:
        enqueue(key)
    except Exception as exc:
        raise QueueUnavailable("The job queue is unavailable. Try again in a moment.") from exc
    return RefreshQueued(key=key, queued=True)


class AreaOut(BaseModel):
    area: str
    organisations: int


class SearchOptions(BaseModel):
    key: str
    loaded: bool
    areas: list[AreaOut]
    london_postcode_areas: list[str]
    attribution: str


@router.get("/{key}/options")
async def options(key: str, _: Researcher, db: DbSession) -> SearchOptions:
    """What the search form offers for a register: its areas of work, with counts."""
    source = SOURCES.get(key)
    if source is None:
        raise NotFound("No such register.")
    return SearchOptions(
        key=key,
        loaded=await search.loaded(db, key),
        areas=[AreaOut(area=a, organisations=n) for a, n in await search.area_counts(db, key)],
        london_postcode_areas=list(LONDON_AREAS),
        attribution=source.attribution,
    )


POSTCODE_AREA = r"^[A-Z]{1,2}$"


class RegisterSearchBody(BaseModel):
    source: str = Field(max_length=40)
    areas: list[Annotated[str, Field(max_length=120)]] = Field(default_factory=list, max_length=20)
    postcode_areas: list[Annotated[str, Field(pattern=POSTCODE_AREA)]] = Field(
        default_factory=list, max_length=40
    )
    offices_min: int | None = Field(default=None, ge=1, le=1000)
    offices_max: int | None = Field(default=None, ge=1, le=1000)
    authorised_since: date | None = None
    max_areas: int | None = Field(default=None, ge=1, le=50)
    with_website: bool = True
    limit: int = Field(default=100, ge=1, le=search.MAX_RESULTS)


@search_router.post("", status_code=status.HTTP_201_CREATED)
async def register_search(body: RegisterSearchBody, user: Researcher, db: DbSession) -> JobDetail:
    """Organisations on a register that match a segment; they become a checked discovery job
    (duplicates, existing accounts and the suppression list are marked)."""
    if body.source not in SOURCES:
        raise NotFound("No such register.")
    if not await search.loaded(db, body.source):
        raise RegisterNotLoaded(
            f"The {SOURCES[body.source].name} register has not been loaded yet. An admin can "
            "refresh it under Settings, Data sources."
        )
    query = search.RegisterQuery(
        source=body.source,
        areas=tuple(body.areas),
        postcode_areas=tuple(body.postcode_areas),
        offices_min=body.offices_min,
        offices_max=body.offices_max,
        authorised_since=body.authorised_since,
        max_areas=body.max_areas,
        with_website=body.with_website,
        limit=body.limit,
    )
    records, total = await search.find(db, query)
    job = await discovery.create_register_search(
        db, user=user, label=query.label(), records=records, total=total
    )
    await db.commit()
    return await _detail(db, job, None)
