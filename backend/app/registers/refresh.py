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
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.core.enums import RegisterRefreshStatus
from app.providers.errors import ProviderError
from app.providers.fetch.netguard import parse_networks
from app.providers.fetch.safe_http import SafeHttpFetcher
from app.providers.fetch.types import FetchBudget
from app.registers.models import RegisterRecord, RegisterSource
from app.registers.sources import RegisterEntry, RegisterSourceAdapter
from app.registers.sra import SraRegister

logger = logging.getLogger(__name__)

SOURCES: dict[str, RegisterSourceAdapter] = {s.key: s for s in (SraRegister(),)}
# A download with fewer than this share of the records last kept is treated as broken.
MIN_SHARE_OF_PREVIOUS = 0.5
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


def fingerprint(entries: list[RegisterEntry]) -> str:
    """SHA-256 of the entries in a fixed order. Registers do not return byte-identical
    downloads (the SRA's order varies between calls), so the parsed content is compared."""
    canonical = sorted(
        (json.dumps(asdict(e), sort_keys=True, default=str) for e in entries), key=str
    )
    return hashlib.sha256("\n".join(canonical).encode()).hexdigest()


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


async def _apply(
    db: AsyncSession, key: str, entries: list[RegisterEntry], now: datetime
) -> RefreshResult:
    kept = {
        r.source_id: r
        for r in (
            await db.execute(select(RegisterRecord).where(RegisterRecord.source == key))
        ).scalars()
    }
    new = updated = removed = 0
    for entry in entries:
        values = _values(entry)
        record = kept.pop(entry.source_id, None)
        if record is None:
            db.add(
                RegisterRecord(
                    source=key,
                    source_id=entry.source_id,
                    first_seen_at=now,
                    last_seen_at=now,
                    **values,
                )
            )
            new += 1
            continue
        changed = record.removed_at is not None or any(
            getattr(record, f) != v for f, v in values.items()
        )
        for f, v in values.items():
            setattr(record, f, v)
        record.last_seen_at = now
        record.removed_at = None
        updated += changed
    for record in kept.values():  # no longer listed
        if record.removed_at is None:
            record.removed_at = now
            record.active = False
            removed += 1
    await db.flush()
    return RefreshResult(
        RegisterRefreshStatus.OK, new=new, updated=updated, removed=removed, records=len(entries)
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
