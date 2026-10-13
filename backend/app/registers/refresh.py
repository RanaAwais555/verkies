"""Keeps VROS's copy of each register current (slice 8.1).

A refresh downloads the whole register through the safe fetcher. A download whose content
matches the last applied one changes nothing. Otherwise every entry is applied: new ones added,
changed ones updated, and ones the register no longer lists are marked removed (never deleted).
A download that fails, cannot be parsed, or is suspiciously short leaves the copy as it was and
says why on the source's status: a failing source is reported, never read as "no records".
"""

import hashlib
import json
import logging
from collections.abc import Iterator
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.core.enums import RegisterRefreshStatus
from app.core.ids import uuid7
from app.providers.errors import ProviderError
from app.providers.fetch.netguard import parse_networks
from app.providers.fetch.safe_http import SafeHttpFetcher
from app.providers.fetch.types import FetchBudget
from app.registers.charity import CharityRegister
from app.registers.gias import SchoolsRegister
from app.registers.iaa import IaaRegister
from app.registers.models import RegisterRecord, RegisterSource
from app.registers.sources import RegisterEntry, RegisterSourceAdapter
from app.registers.sra import SraRegister

logger = logging.getLogger(__name__)

SOURCES: dict[str, RegisterSourceAdapter] = {
    s.key: s for s in (SraRegister(), IaaRegister(), SchoolsRegister(), CharityRegister())
}
# A download with fewer than this share of the records last kept is treated as broken.
MIN_SHARE_OF_PREVIOUS = 0.5
# Rows per SQL statement when applying a download (well under PostgreSQL's parameter limit).
BATCH = 1000
FIELDS = (
    "name",
    "active",
    "status",
    "legal_form",
    "company_number",
    "website",
    "phone",
    "email",
    "postcode",
    "town",
    "postcode_areas",
    "areas",
    "office_count",
    "authorised_on",
    "income",
    "data",
)


@dataclass(frozen=True)
class RefreshResult:
    status: RegisterRefreshStatus
    new: int = 0
    updated: int = 0
    removed: int = 0
    records: int = 0
    error: str | None = None


def build_register_fetcher(settings: Settings) -> SafeHttpFetcher:
    """The safe fetcher with a budget for whole-register downloads."""
    return SafeHttpFetcher(
        user_agent=settings.crawler_user_agent,
        budget=FetchBudget(
            max_bytes=settings.register_max_bytes,
            max_redirects=settings.crawl_max_redirects,
            timeout_seconds=settings.register_timeout_seconds,
            allowed_ports=frozenset(settings.crawl_allowed_ports),
        ),
        allowlist=parse_networks(settings.fetch_private_allowlist),
    )


def _now() -> datetime:
    return datetime.now(UTC)


def row_hash(entry: RegisterEntry) -> str:
    """SHA-256 of one entry's content, so a refresh rewrites only what changed."""
    return hashlib.sha256(
        json.dumps(asdict(entry), sort_keys=True, default=str).encode()
    ).hexdigest()


def fingerprint(entries: list[RegisterEntry]) -> str:
    """SHA-256 of the entries in a fixed order. Registers do not return byte-identical
    downloads (the SRA's order varies between calls), so the parsed content is compared."""
    return hashlib.sha256("\n".join(sorted(map(row_hash, entries))).encode()).hexdigest()


def _values(entry: RegisterEntry) -> dict[str, object]:
    values = asdict(entry)
    values["postcode_areas"] = list(entry.postcode_areas)
    values["areas"] = list(entry.areas)
    return {f: values[f] for f in FIELDS}


async def _source_row(db: AsyncSession, key: str) -> RegisterSource:
    row = await db.get(RegisterSource, key, with_for_update=True)
    if row is None:
        row = RegisterSource(key=key, record_count=0, active_count=0, detail={})
        db.add(row)
        await db.flush()
    return row


async def _finish(
    db: AsyncSession, row: RegisterSource, result: RefreshResult, now: datetime
) -> RefreshResult:
    row.last_checked_at = now
    row.last_status = result.status
    row.last_error = result.error
    await db.commit()
    return result


async def refresh_source(
    key: str,
    sessionmaker: async_sessionmaker[AsyncSession],
    fetcher: SafeHttpFetcher,
    settings: Settings,
    *,
    now: datetime | None = None,
) -> RefreshResult:
    source = SOURCES[key]
    now = now or _now()
    async with sessionmaker() as db:
        row = await _source_row(db, key)
        if not source.configured(settings):
            return await _finish(
                db,
                row,
                RefreshResult(
                    RegisterRefreshStatus.UNCONFIGURED,
                    error="No key on the server for this source.",
                ),
                now,
            )
        try:
            entries = source.parse(await source.download(fetcher, settings))
        except ProviderError as exc:  # includes ProviderUnavailable (refused key, network)
            return await _finish(
                db, row, RefreshResult(RegisterRefreshStatus.FAILED, error=exc.message), now
            )
        digest = fingerprint(entries)
        if digest == row.content_hash:
            return await _finish(
                db,
                row,
                RefreshResult(RegisterRefreshStatus.UNCHANGED, records=row.record_count),
                now,
            )
        if not entries or len(entries) < row.record_count * MIN_SHARE_OF_PREVIOUS:
            return await _finish(
                db,
                row,
                RefreshResult(
                    RegisterRefreshStatus.FAILED,
                    error=f"The download listed {len(entries)} organisations, against "
                    f"{row.record_count} last time; the copy kept was left as it was.",
                ),
                now,
            )
        result = await _apply(db, key, entries, now)
        row.content_hash = digest
        row.last_changed_at = now
        row.record_count = len(entries)
        row.active_count = sum(1 for e in entries if e.active)
        row.detail = {"new": result.new, "updated": result.updated, "removed": result.removed}
        logger.info("register refreshed", extra={"source": key, **row.detail})
        return await _finish(db, row, result, now)


def _chunks[T](items: list[T], size: int = BATCH) -> Iterator[list[T]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]


async def _apply(
    db: AsyncSession, key: str, entries: list[RegisterEntry], now: datetime
) -> RefreshResult:
    """Apply a download in batches of plain SQL, so a register of hundreds of thousands of
    organisations never needs one ORM object each: only new or changed rows are written in
    full, unchanged ones just get last_seen_at, and ones no longer listed are marked removed."""
    kept = {
        source_id: (digest, removed_at)
        for source_id, digest, removed_at in (
            await db.execute(
                select(
                    RegisterRecord.source_id, RegisterRecord.row_hash, RegisterRecord.removed_at
                ).where(RegisterRecord.source == key)
            )
        ).all()
    }
    writes: list[dict[str, Any]] = []
    unchanged: list[str] = []
    new = updated = 0
    for entry in entries:
        digest = row_hash(entry)
        previous = kept.pop(entry.source_id, None)
        if previous is not None and previous == (digest, None):
            unchanged.append(entry.source_id)
            continue
        if previous is None:
            new += 1
        else:
            updated += 1
        writes.append(
            {
                "id": uuid7(),
                "source": key,
                "source_id": entry.source_id,
                "row_hash": digest,
                "first_seen_at": now,
                "last_seen_at": now,
                "removed_at": None,
                **_values(entry),
            }
        )
    for rows in _chunks(writes):
        stmt = insert(RegisterRecord).values(rows)
        refreshed = {f: stmt.excluded[f] for f in (*FIELDS, "row_hash", "last_seen_at")}
        await db.execute(
            stmt.on_conflict_do_update(
                index_elements=["source", "source_id"],
                set_={**refreshed, "removed_at": None, "updated_at": func.now()},
            )
        )
    for ids in _chunks(unchanged):
        await db.execute(
            update(RegisterRecord)
            .where(RegisterRecord.source == key, RegisterRecord.source_id.in_(ids))
            .values(last_seen_at=now)
            .execution_options(synchronize_session=False)
        )
    gone = [source_id for source_id, (_, removed_at) in kept.items() if removed_at is None]
    for ids in _chunks(gone):  # no longer listed
        await db.execute(
            update(RegisterRecord)
            .where(RegisterRecord.source == key, RegisterRecord.source_id.in_(ids))
            .values(removed_at=now, active=False, updated_at=func.now())
            .execution_options(synchronize_session=False)
        )
    return RefreshResult(
        RegisterRefreshStatus.OK,
        new=new,
        updated=updated,
        removed=len(gone),
        records=len(entries),
    )


def due(row: RegisterSource | None, source: RegisterSourceAdapter, now: datetime) -> bool:
    """Checked less recently than the source's cadence (an hour's slack for the schedule). A
    failed refresh is tried again on the next hourly run."""
    if (
        row is None
        or row.last_checked_at is None
        or row.last_status == RegisterRefreshStatus.FAILED
    ):
        return True
    return now - row.last_checked_at >= timedelta(hours=source.cadence_hours - 1)


async def refresh_due(
    sessionmaker: async_sessionmaker[AsyncSession],
    fetcher: SafeHttpFetcher,
    settings: Settings,
    *,
    now: datetime | None = None,
) -> dict[str, str]:
    """The worker's scheduled run: refresh every source that is due."""
    now = now or _now()
    async with sessionmaker() as db:
        rows = {r.key: r for r in (await db.execute(select(RegisterSource))).scalars()}
    report: dict[str, str] = {}
    for key, source in SOURCES.items():
        if not due(rows.get(key), source, now):
            report[key] = "not due"
            continue
        result = await refresh_source(key, sessionmaker, fetcher, settings, now=now)
        report[key] = result.status.value
    return report
