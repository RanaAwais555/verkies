"""/dashboard: the counts behind the charts on Home, computed in the database so they are
exact (not estimated from a capped list), and limited to what the user may see: the same
rules as the research and account lists."""

from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import Date, cast, func, select

from app.accounts import access
from app.accounts.models import Account
from app.auth.deps import CurrentUser, DbSession
from app.core.enums import JobStatus, PriorityBand, ReviewStatus
from app.research.models import ResearchRun
from app.research.service import visible_runs

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

DAYS = 14


class DayCount(BaseModel):
    date: date
    runs: int


class Dashboard(BaseModel):
    days: list[DayCount]
    """Research runs started per UTC day, oldest first, the last DAYS days including today."""
    decisions: dict[ReviewStatus, int]
    """Completed runs by review decision."""
    bands: dict[str, int]
    """Accounts by priority band; "unknown" when an account has no score yet."""


@router.get("")
async def dashboard(user: CurrentUser, db: DbSession) -> Dashboard:
    today = datetime.now(UTC).date()
    first = today - timedelta(days=DAYS - 1)
    runs_clause = visible_runs(user)

    day = cast(func.timezone("UTC", ResearchRun.created_at), Date)
    per_day = select(day, func.count()).where(day >= first).group_by(day)
    if runs_clause is not None:
        per_day = per_day.where(runs_clause)
    counts = {d: n for d, n in (await db.execute(per_day)).all()}

    by_decision = (
        select(ResearchRun.review_status, func.count())
        .where(ResearchRun.status == JobStatus.COMPLETED)
        .group_by(ResearchRun.review_status)
    )
    if runs_clause is not None:
        by_decision = by_decision.where(runs_clause)
    decisions = {s: 0 for s in ReviewStatus} | dict((await db.execute(by_decision)).all())

    by_band = (
        select(Account.priority_band, func.count())
        .where(Account.deleted_at.is_(None))
        .group_by(Account.priority_band)
    )
    if (accounts_clause := access.visible(user)) is not None:
        by_band = by_band.where(accounts_clause)
    bands = {b.value: 0 for b in PriorityBand} | {"unknown": 0}
    for band, n in (await db.execute(by_band)).all():
        bands[band.value if band else "unknown"] = n

    days = [first + timedelta(days=i) for i in range(DAYS)]
    return Dashboard(
        days=[DayCount(date=d, runs=counts.get(d, 0)) for d in days],
        decisions=decisions,
        bands=bands,
    )
