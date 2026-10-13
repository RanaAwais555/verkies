"""Searching a register VROS keeps (slice 8.1): which organisations match a segment, e.g. SRA
firms that do immigration work and have an office in London."""

from dataclasses import dataclass
from datetime import date

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.registers.models import RegisterRecord, RegisterSource
from app.registers.sources import LONDON_AREAS

MAX_RESULTS = 500


def _money(pounds: int) -> str:
    """250000 -> "£250k", 2000000 -> "£2m"."""
    if pounds >= 1_000_000:
        return f"£{pounds / 1_000_000:g}m"
    if pounds >= 1_000:
        return f"£{pounds / 1_000:g}k"
    return f"£{pounds}"


@dataclass(frozen=True)
class RegisterQuery:
    source: str
    # Any of these areas of work (empty: any).
    areas: tuple[str, ...] = ()
    # An office in any of these postcode areas (empty: anywhere).
    postcode_areas: tuple[str, ...] = ()
    offices_min: int | None = None
    offices_max: int | None = None
    authorised_since: date | None = None
    # Firms that list at most this many areas of work: specialists rather than generalists.
    max_areas: int | None = None
    # Latest annual income in pounds (registers that state it: charities).
    income_min: int | None = None
    income_max: int | None = None
    with_website: bool = True
    limit: int = 100

    def label(self, title: str | None = None) -> str:
        parts = [", ".join(self.areas) or "All areas"]
        if set(self.postcode_areas) == set(LONDON_AREAS):
            parts.append("in London")
        elif self.postcode_areas:
            parts.append("in " + ", ".join(self.postcode_areas))
        low, high = self.offices_min, self.offices_max
        if low and high:
            parts.append(f"{low} offices" if low == high else f"{low}-{high} offices")
        elif low:
            parts.append(f"{low}+ offices")
        elif high:
            parts.append(f"up to {high} offices")
        if self.max_areas:
            parts.append(f"at most {self.max_areas} areas of work")
        low_income, high_income = self.income_min, self.income_max
        if low_income and high_income:
            parts.append(f"income {_money(low_income)}-{_money(high_income)}")
        elif low_income:
            parts.append(f"income {_money(low_income)}+")
        elif high_income:
            parts.append(f"income up to {_money(high_income)}")
        if self.authorised_since:
            parts.append(f"authorised since {self.authorised_since.isoformat()}")
        return f"{title or self.source.upper()}: " + "; ".join(parts)


def _filtered(query: RegisterQuery) -> Select[RegisterRecord]:
    stmt = select(RegisterRecord).where(
        RegisterRecord.source == query.source, RegisterRecord.active.is_(True)
    )
    if query.areas:
        stmt = stmt.where(RegisterRecord.areas.overlap(list(query.areas)))
    if query.postcode_areas:
        stmt = stmt.where(RegisterRecord.postcode_areas.overlap(list(query.postcode_areas)))
    if query.offices_min is not None:
        stmt = stmt.where(RegisterRecord.office_count >= query.offices_min)
    if query.offices_max is not None:
        stmt = stmt.where(RegisterRecord.office_count <= query.offices_max)
    if query.authorised_since is not None:
        stmt = stmt.where(RegisterRecord.authorised_on >= query.authorised_since)
    if query.max_areas is not None:
        stmt = stmt.where(func.cardinality(RegisterRecord.areas) <= query.max_areas)
    if query.income_min is not None:
        stmt = stmt.where(RegisterRecord.income >= query.income_min)
    if query.income_max is not None:
        stmt = stmt.where(RegisterRecord.income <= query.income_max)
    if query.with_website:
        stmt = stmt.where(RegisterRecord.website.is_not(None))
    return stmt


async def find(db: AsyncSession, query: RegisterQuery) -> tuple[list[RegisterRecord], int]:
    """Matching organisations (up to the limit, by name) and how many match in all."""
    stmt = _filtered(query)
    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    rows = (
        await db.execute(
            stmt.order_by(RegisterRecord.name, RegisterRecord.source_id).limit(
                min(query.limit, MAX_RESULTS)
            )
        )
    ).scalars()
    return list(rows), total


async def area_counts(db: AsyncSession, source: str) -> list[tuple[str, int]]:
    """Each area of work among active organisations, with how many list it."""
    area = func.unnest(RegisterRecord.areas).label("area")
    inner = (
        select(area)
        .where(RegisterRecord.source == source, RegisterRecord.active.is_(True))
        .subquery()
    )
    rows = await db.execute(
        select(inner.c.area, func.count()).group_by(inner.c.area).order_by(func.count().desc())
    )
    return [(str(a), int(n)) for a, n in rows.all()]


async def loaded(db: AsyncSession, source: str) -> bool:
    row = await db.get(RegisterSource, source)
    return bool(row and row.record_count)
