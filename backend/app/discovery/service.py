"""CSV import (§16): upload, map columns, check every row (validation, duplicates, suppression)
and start research on the rows a person picks. Nothing becomes an Account here."""

import uuid
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy import String, column, func, select, values
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounts.models import Account, AccountDomain, Suppression
from app.audit import service as audit
from app.auth.models import User
from app.config import Settings
from app.core.enums import (
    AuditSource,
    CandidateStatus,
    DiscoveryKind,
    DiscoveryStatus,
    SuppressionKind,
)
from app.core.errors import Conflict, NotFound, ValidationFailed
from app.discovery import csv_import
from app.discovery.models import DiscoveredCompany, DiscoveryJob
from app.research import service as research
from app.research.models import ResearchRun
from app.research.urls import normalised_domain

NAME_SIMILARITY = 0.6  # same threshold as approval's duplicate check (DATA_MODEL.md §3)
MAX_RESEARCH_PER_REQUEST = 50
RESEARCHABLE = frozenset({CandidateStatus.NEW, CandidateStatus.POSSIBLE_DUPLICATE})
SEE_ALL = "accounts.read"


async def create_import(
    db: AsyncSession, *, user: User, filename: str, content: str
) -> DiscoveryJob:
    parsed = csv_import.parse(content)
    job = DiscoveryJob(
        kind=DiscoveryKind.CSV_IMPORT,
        name=(filename.strip() or "Upload")[:200],
        created_by_id=user.id,
        status=DiscoveryStatus.UPLOADED,
        columns=parsed.columns,
        mapping=csv_import.guess_mapping(parsed.columns),
        row_count=len(parsed.rows),
        stats={},
    )
    db.add(job)
    await db.flush()
    for i, row in enumerate(parsed.rows, start=1):
        db.add(DiscoveredCompany(discovery_job_id=job.id, row_number=i, raw=row))
    audit.record(
        db,
        action="discovery.imported",
        object_table="discovery_jobs",
        object_id=job.id,
        user_id=user.id,
        source=AuditSource.API,
        new_value={"file": job.name, "rows": job.row_count},
    )
    return job


SEARCH_COLUMNS = ["name", "website", "notes", "source_url"]
SEARCH_MAPPING = {"name": "name", "website": "website", "notes": "notes"}


async def create_search(
    db: AsyncSession, *, user: User, query: str, rows: list[dict[str, str]]
) -> DiscoveryJob:
    """A discovery job from web search results, checked like an import (duplicates,
    suppression, previous research) so the reviewer only picks among new companies."""
    if not rows:
        raise ValidationFailed(
            "The search found no company websites (directories, social networks and news "
            "sites are left out). Try different words."
        )
    job = DiscoveryJob(
        kind=DiscoveryKind.SEARCH,
        name=query.strip()[:200],
        created_by_id=user.id,
        status=DiscoveryStatus.UPLOADED,
        columns=SEARCH_COLUMNS,
        mapping=SEARCH_MAPPING,
        row_count=len(rows),
        stats={},
    )
    db.add(job)
    await db.flush()
    for i, row in enumerate(rows, start=1):
        db.add(DiscoveredCompany(discovery_job_id=job.id, row_number=i, raw=row))
    await db.flush()
    audit.record(
        db,
        action="discovery.searched",
        object_table="discovery_jobs",
        object_id=job.id,
        user_id=user.id,
        source=AuditSource.API,
        new_value={"query": job.name, "results": len(rows)},
    )
    await check(db, user=user, job=job, mapping=SEARCH_MAPPING)
    return job


async def get_job(db: AsyncSession, *, user: User, job_id: uuid.UUID) -> DiscoveryJob:
    job = await db.get(DiscoveryJob, job_id)
    if job is None or (job.created_by_id != user.id and SEE_ALL not in user.permission_keys):
        raise NotFound("Import not found.")
    return job


async def list_jobs(db: AsyncSession, *, user: User, limit: int) -> list[DiscoveryJob]:
    stmt = select(DiscoveryJob).order_by(DiscoveryJob.created_at.desc()).limit(limit)
    if SEE_ALL not in user.permission_keys:
        stmt = stmt.where(DiscoveryJob.created_by_id == user.id)
    return list((await db.execute(stmt)).scalars())


async def rows_of(
    db: AsyncSession, job: DiscoveryJob, status: CandidateStatus | None = None
) -> list[DiscoveredCompany]:
    stmt = (
        select(DiscoveredCompany)
        .where(DiscoveredCompany.discovery_job_id == job.id)
        .order_by(DiscoveredCompany.row_number)
    )
    if status is not None:
        stmt = stmt.where(DiscoveredCompany.status == status)
    return list((await db.execute(stmt)).scalars())


def _cell(row: DiscoveredCompany, mapping: dict[str, str], field: str, limit: int) -> str | None:
    col = mapping.get(field)
    value = str(row.raw.get(col, "")).strip() if col else ""
    return value[:limit] or None


@dataclass
class _Lookups:
    accounts_by_domain: dict[str, uuid.UUID]
    suppressed: set[str]
    runs_by_domain: dict[str, ResearchRun]
    similar_names: dict[str, tuple[uuid.UUID, str, float]]


async def _lookups(db: AsyncSession, domains: set[str], names: set[str]) -> _Lookups:
    accounts_by_domain: dict[str, uuid.UUID] = {}
    suppressed: set[str] = set()
    runs_by_domain: dict[str, ResearchRun] = {}
    if domains:
        found = await db.execute(
            select(AccountDomain.domain, AccountDomain.account_id)
            .join(Account, Account.id == AccountDomain.account_id)
            .where(AccountDomain.domain.in_(domains), Account.deleted_at.is_(None))
        )
        accounts_by_domain = {d: a for d, a in found.all()}
        suppressed = set(
            (
                await db.execute(
                    select(Suppression.value).where(
                        Suppression.kind == SuppressionKind.DOMAIN, Suppression.value.in_(domains)
                    )
                )
            ).scalars()
        )
        runs = (
            await db.execute(
                select(ResearchRun)
                .where(ResearchRun.normalised_domain.in_(domains))
                .order_by(ResearchRun.created_at)
            )
        ).scalars()
        for run in runs:  # the latest run per domain wins
            runs_by_domain[run.normalised_domain] = run
    similar: dict[str, tuple[uuid.UUID, str, float]] = {}
    if names:
        given = values(column("name", String), name="given").data([(n,) for n in names])
        score = func.similarity(Account.name, given.c.name)
        found_names = await db.execute(
            select(given.c.name, Account.id, Account.name, score)
            .join(Account, Account.name.op("%")(given.c.name))
            .where(Account.deleted_at.is_(None), score >= NAME_SIMILARITY)
        )
        for given_name, account_id, account_name, sim in found_names.all():
            if given_name not in similar or sim > similar[given_name][2]:
                similar[given_name] = (account_id, account_name, float(sim))
    return _Lookups(accounts_by_domain, suppressed, runs_by_domain, similar)


async def check(
    db: AsyncSession, *, user: User, job: DiscoveryJob, mapping: dict[str, str]
) -> DiscoveryJob:
    """Apply the column mapping and sort every row into exactly one status. Rows already sent
    to research keep their status."""
    job.mapping = csv_import.validate_mapping(mapping, job.columns)
    rows = await rows_of(db, job)
    parsed: dict[uuid.UUID, tuple[str | None, str | None]] = {}
    for row in rows:
        row.name = _cell(row, job.mapping, "name", 300)
        row.website_url = _cell(row, job.mapping, "website", 2000)
        row.country = _cell(row, job.mapping, "country", 120)
        row.industry = _cell(row, job.mapping, "industry", 120)
        row.notes = _cell(row, job.mapping, "notes", 2000)
        if row.status == CandidateStatus.QUEUED:
            continue
        domain, problem = None, None
        if not row.website_url:
            problem = "No website in this row."
        else:
            try:
                _, domain = normalised_domain(row.website_url)
            except ValidationFailed as exc:
                problem = exc.message
        parsed[row.id] = (domain, problem)

    domains = {d for d, _ in parsed.values() if d}
    names = {r.name for r in rows if r.name and r.id in parsed}
    found = await _lookups(db, domains, names)

    first_row: dict[str, int] = {
        r.normalised_domain: r.row_number
        for r in reversed(rows)
        if r.status == CandidateStatus.QUEUED and r.normalised_domain
    }
    for row in rows:
        if row.id not in parsed:
            continue
        domain, problem = parsed[row.id]
        row.normalised_domain = domain
        row.matched_account_id = None
        row.research_run_id = None
        if problem or not domain:
            row.status, row.status_detail = CandidateStatus.INVALID, problem
        elif domain in found.suppressed:
            row.status, row.status_detail = (
                CandidateStatus.SUPPRESSED,
                "On the do-not-contact list.",
            )
        elif domain in first_row:
            row.status = CandidateStatus.DUPLICATE_IN_FILE
            row.status_detail = f"Same website as row {first_row[domain]}."
        elif domain in found.accounts_by_domain:
            row.status = CandidateStatus.EXISTING_ACCOUNT
            row.matched_account_id = found.accounts_by_domain[domain]
            row.status_detail = "This website already belongs to an account."
        elif domain in found.runs_by_domain:
            run = found.runs_by_domain[domain]
            row.status = CandidateStatus.ALREADY_RESEARCHED
            row.research_run_id = run.id
            row.status_detail = (
                f"Researched before ({run.status.value}, {run.review_status.value})."
            )
        elif row.name and row.name in found.similar_names:
            account_id, account_name, sim = found.similar_names[row.name]
            row.status = CandidateStatus.POSSIBLE_DUPLICATE
            row.matched_account_id = account_id
            row.status_detail = f"Similar name to the account {account_name} ({sim:.0%})."
        else:
            row.status, row.status_detail = CandidateStatus.NEW, None
        if domain and domain not in first_row:
            first_row[domain] = row.row_number

    job.status = DiscoveryStatus.CHECKED
    job.stats = dict(Counter(r.status.value for r in rows))
    audit.record(
        db,
        action="discovery.checked",
        object_table="discovery_jobs",
        object_id=job.id,
        user_id=user.id,
        source=AuditSource.API,
        new_value={"mapping": job.mapping, "stats": job.stats},
    )
    return job


async def start_research(
    db: AsyncSession,
    *,
    user: User,
    job: DiscoveryJob,
    row_ids: list[uuid.UUID],
    settings: Settings,
) -> tuple[list[ResearchRun], dict[str, str]]:
    """Start research on the chosen rows. Returns the new runs and, per skipped row id, why."""
    if job.status != DiscoveryStatus.CHECKED:
        raise Conflict("Map the columns and check the rows first.")
    if len(row_ids) > MAX_RESEARCH_PER_REQUEST:
        raise ValidationFailed(f"Start at most {MAX_RESEARCH_PER_REQUEST} at a time.")
    rows = list(
        (
            await db.execute(
                select(DiscoveredCompany)
                .where(
                    DiscoveredCompany.discovery_job_id == job.id,
                    DiscoveredCompany.id.in_(row_ids),
                )
                .with_for_update()
            )
        ).scalars()
    )
    found = {r.id for r in rows}
    skipped = {str(i): "Not in this import." for i in row_ids if i not in found}
    runs: list[ResearchRun] = []
    for row in sorted(rows, key=lambda r: r.row_number):
        if row.status not in RESEARCHABLE or not row.website_url:
            skipped[str(row.id)] = f"Row {row.row_number} is {row.status.value.replace('_', ' ')}."
            continue
        try:
            async with db.begin_nested():
                run = await research.start_run(
                    db, user=user, url=row.website_url, settings=settings
                )
        except (Conflict, ValidationFailed) as exc:
            skipped[str(row.id)] = exc.message
            continue
        row.status = CandidateStatus.QUEUED
        row.research_run_id = run.id
        row.status_detail = None
        runs.append(run)
    job.stats = dict(Counter(r.status.value for r in await rows_of(db, job)))
    return runs, skipped


async def enqueue_all(
    db: AsyncSession, runs: list[ResearchRun], enqueue: Callable[[uuid.UUID], None]
) -> int:
    """Hand the committed runs to the worker; a queue outage fails those runs cleanly."""
    failed = 0
    for run in runs:
        try:
            enqueue(run.id)
        except Exception:
            await research.mark_enqueue_failed(db, run)
            failed += 1
    if failed:
        await db.commit()
    return failed


async def run_states(
    db: AsyncSession, rows: list[DiscoveredCompany]
) -> dict[uuid.UUID, ResearchRun]:
    ids = {r.research_run_id for r in rows if r.research_run_id}
    if not ids:
        return {}
    return {
        run.id: run
        for run in (await db.execute(select(ResearchRun).where(ResearchRun.id.in_(ids)))).scalars()
    }
