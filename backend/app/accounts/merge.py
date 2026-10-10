"""Duplicate review and account merge (§16, slice 2.6).

Duplicates are only ever suggested; a person merges them. A merge moves the mutable records
(domains, identifiers, contacts, leads, opportunities, tasks, activities, research, briefs,
discovery matches) to the account being kept, fills the kept account's empty fields from the other
one, and retires the other account: it is soft-deleted and points at the survivor. Append-only
history (evidence, claims, observations, score snapshots, timeline) cannot move, so it stays on
the retired account and is read together with the survivor (`family_ids`).
"""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Select, and_, delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.accounts import access
from app.accounts.models import (
    Account,
    AccountDomain,
    AccountDuplicateDismissal,
    AccountIdentifier,
    Contact,
)
from app.audit import service as audit
from app.auth.models import User
from app.briefs.models import LeadBrief
from app.core.enums import AuditSource
from app.core.errors import AppError, Conflict, NotFound
from app.crm import timeline
from app.crm.models import Activity, Lead, Opportunity, Task
from app.discovery.models import DiscoveredCompany
from app.research.models import ResearchRun

NAME_SIMILARITY = 0.6  # the pg_trgm threshold used everywhere duplicates are looked up (§16)

# Fields the kept account takes from the merged one when it has no value of its own.
FILLABLE = (
    "legal_name",
    "website_url",
    "industry",
    "sub_industry",
    "business_model",
    "description",
    "hq_city",
    "hq_country",
    "company_size_band",
    "linkedin_company_url",
    "owner_id",
)

# Mutable tables whose rows follow the account they belong to.
MOVABLE: tuple[tuple[Any, Any], ...] = (
    (AccountIdentifier, AccountIdentifier.account_id),
    (Contact, Contact.account_id),
    (Lead, Lead.account_id),
    (Opportunity, Opportunity.account_id),
    (Task, Task.account_id),
    (Activity, Activity.account_id),
    (ResearchRun, ResearchRun.account_id),
    (LeadBrief, LeadBrief.account_id),
    (DiscoveredCompany, DiscoveredCompany.matched_account_id),
)


@dataclass
class DuplicatePair:
    a: Account
    b: Account
    reasons: list[str] = field(default_factory=list)
    similarity: float | None = None


def _ordered(x: uuid.UUID, y: uuid.UUID) -> tuple[uuid.UUID, uuid.UUID]:
    return (x, y) if x < y else (y, x)


def _stem(domain: str | None) -> str | None:
    """The registrable name without its ending: harbour.co.uk and harbour.com share "harbour"."""
    return domain.split(".", 1)[0] if domain else None


async def family_ids(db: AsyncSession, account_id: uuid.UUID) -> list[uuid.UUID]:
    """The account and every account merged into it (merges re-point chains, so one level)."""
    merged = (
        await db.execute(select(Account.id).where(Account.merged_into_id == account_id))
    ).scalars()
    return [account_id, *merged]


async def find_duplicates(db: AsyncSession, *, user: User, limit: int = 50) -> list[DuplicatePair]:
    """Live account pairs that look like the same company and nobody has dismissed: similar
    names, the same legal name, or the same domain name under a different ending."""
    a, b = aliased(Account), aliased(Account)
    sim = func.similarity(a.name, b.name)
    stmt: Select[Any] = (
        select(a, b, sim)
        .join(b, a.id < b.id)
        .where(
            a.deleted_at.is_(None),
            b.deleted_at.is_(None),
            or_(
                sim >= NAME_SIMILARITY,
                and_(
                    a.legal_name.is_not(None), func.lower(a.legal_name) == func.lower(b.legal_name)
                ),
                and_(
                    a.primary_domain.is_not(None),
                    b.primary_domain.is_not(None),
                    func.split_part(a.primary_domain, ".", 1)
                    == func.split_part(b.primary_domain, ".", 1),
                ),
            ),
            ~select(AccountDuplicateDismissal.id)
            .where(
                AccountDuplicateDismissal.account_a_id == a.id,
                AccountDuplicateDismissal.account_b_id == b.id,
            )
            .exists(),
        )
        .order_by(sim.desc(), a.name)
        .limit(limit)
    )
    clause = access.visible(user)
    if clause is not None:
        visible = select(Account.id).where(clause)
        stmt = stmt.where(a.id.in_(visible), b.id.in_(visible))
    pairs: list[DuplicatePair] = []
    for first, second, similarity in (await db.execute(stmt)).all():
        pair = DuplicatePair(first, second, similarity=round(float(similarity), 2))
        if similarity >= NAME_SIMILARITY:
            pair.reasons.append(f"Similar names ({similarity:.0%} alike)")
        if (
            first.legal_name
            and second.legal_name
            and first.legal_name.lower() == second.legal_name.lower()
        ):
            pair.reasons.append("Same legal name")
        if (
            first.primary_domain
            and second.primary_domain
            and _stem(first.primary_domain) == _stem(second.primary_domain)
        ):
            pair.reasons.append(
                f"Same website name: {first.primary_domain} and {second.primary_domain}"
            )
        pairs.append(pair)
    return pairs


async def _live(db: AsyncSession, user: User, account_id: uuid.UUID) -> Account:
    account = await db.get(Account, account_id, with_for_update=True)
    if (
        account is None
        or account.deleted_at is not None
        or not access.can_see(user, account.owner_id)
    ):
        raise NotFound("Account not found.")
    return account


async def dismiss(
    db: AsyncSession, *, user: User, first_id: uuid.UUID, second_id: uuid.UUID, reason: str | None
) -> None:
    if first_id == second_id:
        raise AppError("Choose two different accounts.")
    await _live(db, user, first_id)
    await _live(db, user, second_id)
    a_id, b_id = _ordered(first_id, second_id)
    exists = (
        await db.execute(
            select(AccountDuplicateDismissal.id).where(
                AccountDuplicateDismissal.account_a_id == a_id,
                AccountDuplicateDismissal.account_b_id == b_id,
            )
        )
    ).scalar_one_or_none()
    if exists is None:
        db.add(
            AccountDuplicateDismissal(
                account_a_id=a_id, account_b_id=b_id, dismissed_by_id=user.id, reason=reason
            )
        )
    audit.record(
        db,
        action="account.duplicate_dismissed",
        object_table="accounts",
        object_id=a_id,
        user_id=user.id,
        source=AuditSource.API,
        new_value={"account_a_id": str(a_id), "account_b_id": str(b_id)},
        reason=reason,
    )
    await db.commit()


@dataclass
class MergeResult:
    kept: Account
    retired_id: uuid.UUID
    moved: dict[str, int]
    filled: list[str]


async def merge(
    db: AsyncSession, *, user: User, keep_id: uuid.UUID, merge_id: uuid.UUID, reason: str
) -> MergeResult:
    """Merge `merge_id` into `keep_id` in one transaction, audited and on the timeline."""
    if keep_id == merge_id:
        raise AppError("An account cannot be merged into itself.")
    keep = await _live(db, user, keep_id)
    gone = await _live(db, user, merge_id)
    if gone.merged_into_id is not None or keep.merged_into_id is not None:
        raise Conflict("One of these accounts was already merged.")

    moved: dict[str, int] = {}
    # Domains first: the kept account keeps its primary domain, the others become extra domains.
    result = await db.execute(
        update(AccountDomain)
        .where(AccountDomain.account_id == gone.id)
        .values(account_id=keep.id, is_primary=False)
    )
    moved["account_domains"] = result.rowcount  # type: ignore[attr-defined]
    for model, column in MOVABLE:
        result = await db.execute(
            update(model).where(column == gone.id).values({column.key: keep.id})
        )
        moved[model.__tablename__] = result.rowcount  # type: ignore[attr-defined]

    filled = [
        name for name in FILLABLE if getattr(keep, name) is None and getattr(gone, name) is not None
    ]
    for name in filled:
        setattr(keep, name, getattr(gone, name))
    if gone.next_activity_at and (
        keep.next_activity_at is None or gone.next_activity_at < keep.next_activity_at
    ):
        keep.next_activity_at = gone.next_activity_at
    if gone.last_activity_at and (
        keep.last_activity_at is None or gone.last_activity_at > keep.last_activity_at
    ):
        keep.last_activity_at = gone.last_activity_at

    now = datetime.now(UTC)
    # Accounts merged into the retired one earlier now point straight at the survivor.
    await db.execute(
        update(Account).where(Account.merged_into_id == gone.id).values(merged_into_id=keep.id)
    )
    gone.merged_into_id = keep.id
    gone.deleted_at = now
    await db.execute(
        delete(AccountDuplicateDismissal).where(
            or_(
                AccountDuplicateDismissal.account_a_id == gone.id,
                AccountDuplicateDismissal.account_b_id == gone.id,
            )
        )
    )

    timeline.add(
        db,
        account_id=keep.id,
        event_type="account.merged",
        summary=f"{gone.name} ({gone.primary_domain or 'no website'}) merged into this account.",
        actor_id=user.id,
        ref_table="accounts",
        ref_id=gone.id,
    )
    audit.record(
        db,
        action="account.merged",
        object_table="accounts",
        object_id=keep.id,
        user_id=user.id,
        source=AuditSource.API,
        old_value={
            "merged_account_id": str(gone.id),
            "name": gone.name,
            "primary_domain": gone.primary_domain,
        },
        new_value={"moved": moved, "filled": filled},
        reason=reason,
    )
    await db.commit()
    await db.refresh(keep)
    return MergeResult(kept=keep, retired_id=gone.id, moved=moved, filled=filled)
