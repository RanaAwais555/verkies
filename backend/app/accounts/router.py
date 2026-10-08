"""/accounts: the account list and Account 360 (overview, leads, opportunities, contacts,
tasks, research, timeline, audit)."""

import csv
import io
import json
import uuid
from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Response

from app.accounts import service
from app.accounts.schemas import (
    SCORES,
    Account360Out,
    AccountSummaryOut,
    ContactOut,
    LeadOut,
    RunSummaryOut,
    TimelineEventOut,
    as_float,
    owner_of,
)
from app.audit import service as audit
from app.audit.router import AuditEntryOut
from app.auth.deps import DbSession, require_permission
from app.auth.models import User
from app.core.enums import AccountType, AuditSource
from app.crm.schemas import OpportunityOut, TaskOut
from app.discovery.csv_import import csv_safe

router = APIRouter(prefix="/accounts", tags=["accounts"])

Member = Annotated[User, Depends(require_permission("accounts.read", "accounts.read_own"))]
Auditor = Annotated[User, Depends(require_permission("audit.read"))]


@router.get("")
async def list_accounts(
    user: Member,
    db: DbSession,
    q: Annotated[str | None, Query(max_length=200)] = None,
    account_type: AccountType | None = None,
    owner: Literal["me", "unassigned"] | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[AccountSummaryOut]:
    accounts = await service.list_accounts(
        db,
        user=user,
        query=q,
        account_type=account_type,
        owner=owner,
        limit=limit,
        offset=offset,
    )
    names = await service.user_names(db, {a.owner_id for a in accounts if a.owner_id})
    open_tasks = await service.count_open_tasks(db, [a.id for a in accounts])
    return [AccountSummaryOut.of(a, names, open_tasks.get(a.id, 0)) for a in accounts]


EXPORT_FIELDS = (
    "id",
    "name",
    "primary_domain",
    "website_url",
    "industry",
    "hq_city",
    "hq_country",
    "account_type",
    "owner",
    "priority_score",
    "priority_band",
    "next_activity_at",
    "created_at",
)


@router.get("/export")
async def export_accounts(
    user: Member,
    db: DbSession,
    format: Literal["csv", "json"] = "csv",
    q: Annotated[str | None, Query(max_length=200)] = None,
) -> Response:
    """Every account the user may see, as CSV (spreadsheet-safe) or JSON. Audited."""
    accounts = await service.list_accounts(
        db, user=user, query=q, account_type=None, owner=None, limit=100_000, offset=0
    )
    names = await service.user_names(db, {a.owner_id for a in accounts if a.owner_id})
    records = [
        {
            "id": str(a.id),
            "name": a.name,
            "primary_domain": a.primary_domain,
            "website_url": a.website_url,
            "industry": a.industry,
            "hq_city": a.hq_city,
            "hq_country": a.hq_country,
            "account_type": a.account_type.value,
            "owner": names.get(a.owner_id) if a.owner_id else None,
            "priority_score": as_float(a.priority_score),
            "priority_band": a.priority_band.value if a.priority_band else None,
            "next_activity_at": a.next_activity_at.isoformat() if a.next_activity_at else None,
            "created_at": a.created_at.isoformat(),
        }
        for a in accounts
    ]
    audit.record(
        db,
        action="accounts.exported",
        object_table="accounts",
        object_id=None,
        user_id=user.id,
        source=AuditSource.API,
        new_value={"format": format, "count": len(records), "query": q},
    )
    await db.commit()
    stamp = datetime.now(UTC).strftime("%Y%m%d")
    if format == "json":
        return Response(
            json.dumps(records, indent=2),
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="vros-accounts-{stamp}.json"'},
        )
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(EXPORT_FIELDS)
    for record in records:
        writer.writerow([csv_safe(record[f]) for f in EXPORT_FIELDS])
    return Response(
        out.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="vros-accounts-{stamp}.csv"'},
    )


@router.get("/{account_id}")
async def account_360(account_id: uuid.UUID, user: Member, db: DbSession) -> Account360Out:
    account = await service.get_account(db, user=user, account_id=account_id)
    found = await service.account_360(db, account)
    names = found["owners"]
    open_tasks = sum(1 for t in found["tasks"] if t.status.value in ("open", "in_progress"))
    return Account360Out(
        **AccountSummaryOut.of(account, names, open_tasks).model_dump(),
        legal_name=account.legal_name,
        website_url=account.website_url,
        description=account.description,
        hq_city=account.hq_city,
        company_size_band=account.company_size_band,
        source=account.source,
        linkedin_company_url=account.linkedin_company_url,
        domains=[d.domain for d in found["domains"]],
        scores={name: as_float(getattr(account, name)) for name in SCORES},
        leads=[
            LeadOut(
                id=lead.id,
                research_run_id=lead.research_run_id,
                source=lead.source,
                status=lead.status.value,
                owner=owner_of(lead.owner_id, names),
                priority_score=as_float(lead.priority_score),
                priority_band=lead.priority_band.value if lead.priority_band else None,
                qualified_at=lead.qualified_at,
                created_at=lead.created_at,
            )
            for lead in found["leads"]
        ],
        opportunities=[
            OpportunityOut.of(o, reasons, labels=found["labels"])
            for o, reasons in found["opportunities"]
        ],
        contacts=[ContactOut.of(c) for c in found["contacts"]],
        tasks=[
            TaskOut.of(t, owner_name=names.get(t.owner_id) if t.owner_id else None)
            for t in found["tasks"]
        ],
        research_runs=[RunSummaryOut.of(r) for r in found["research_runs"]],
        latest_brief_run_id=found["latest_brief_run_id"],
    )


@router.get("/{account_id}/timeline")
async def timeline(
    account_id: uuid.UUID,
    user: Member,
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[TimelineEventOut]:
    account = await service.get_account(db, user=user, account_id=account_id)
    events = await service.timeline_of(db, account.id, limit)
    names = await service.user_names(db, {e.actor_id for e in events if e.actor_id})
    return [
        TimelineEventOut(
            id=e.id,
            occurred_at=e.occurred_at,
            event_type=e.event_type,
            summary=e.summary,
            ref_table=e.ref_table,
            ref_id=e.ref_id,
            actor=owner_of(e.actor_id, names),
        )
        for e in events
    ]


@router.get("/{account_id}/audit")
async def account_audit(
    account_id: uuid.UUID,
    user: Auditor,
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[AuditEntryOut]:
    account = await service.get_account(db, user=user, account_id=account_id)
    return [
        AuditEntryOut.model_validate(r, from_attributes=True)
        for r in await service.audit_of(db, account, limit)
    ]
