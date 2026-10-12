"""Referral management (master context §14; slice 4.3).

A referral records who sent a company to Verkies: the referrer (an account and person in VROS, or
just a name), how they know Verkies, the referred company and its website. The referred company
is matched to its account by website domain whenever it is read, so a referral logged before the
company was researched links up once it is. Converted means a deal on the referred company was won
on or after the referral date; revenue is the sum of those deals' values, per currency, with deals
that have no value counted separately and never as zero.
"""

import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time
from decimal import Decimal
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounts import access
from app.accounts.models import Account, AccountDomain, Contact
from app.audit import service as audit
from app.auth.models import User
from app.clients.models import Referral
from app.core.enums import AuditSource, ReferralStatus, StageOutcome
from app.core.errors import NotFound, ValidationFailed
from app.crm import timeline
from app.deals.models import Deal
from app.research.urls import normalised_domain


def _today() -> date:
    return datetime.now(UTC).date()


def clean_domain(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    return normalised_domain(value)[1]


@dataclass
class ReferralView:
    referral: Referral
    referrer: Account | None
    referred: Account | None  # matched by domain, when the user may see it
    won_deals: int = 0
    revenue: dict[str, Decimal] = field(default_factory=dict)
    unknown_value_deals: int = 0
    recorded_by: str | None = None

    @property
    def converted(self) -> bool:
        return self.won_deals > 0


def _visible_referrals(user: User) -> Any:
    """A referral is visible when its referrer account is, or when it has no referrer account."""
    clause = access.visible(user)
    if clause is None:
        return None
    return or_(Referral.referrer_account_id.is_(None), clause)


async def _views(db: AsyncSession, user: User, referrals: list[Referral]) -> list[ReferralView]:
    if not referrals:
        return []
    domains = {r.referred_domain for r in referrals if r.referred_domain}
    by_domain: dict[str, Account] = {}
    if domains:
        live = (Account.deleted_at.is_(None), Account.merged_into_id.is_(None))
        found: list[Any] = list(
            (
                await db.execute(
                    select(AccountDomain.domain, Account)
                    .join(Account, Account.id == AccountDomain.account_id)
                    .where(AccountDomain.domain.in_(domains), *live)
                )
            ).all()
        )
        found += (
            await db.execute(
                select(Account.primary_domain, Account).where(
                    Account.primary_domain.in_(domains), *live
                )
            )
        ).all()
        for domain, account in found:
            if domain and access.can_see(user, account.owner_id):
                by_domain[domain] = account
    referrer_ids = {r.referrer_account_id for r in referrals if r.referrer_account_id}
    referrers = (
        {
            a.id: a
            for a in (
                await db.execute(select(Account).where(Account.id.in_(referrer_ids)))
            ).scalars()
        }
        if referrer_ids
        else {}
    )
    won: dict[uuid.UUID, list[Deal]] = defaultdict(list)
    if by_domain:
        for deal in (
            await db.execute(
                select(Deal).where(
                    Deal.account_id.in_([a.id for a in by_domain.values()]),
                    Deal.deleted_at.is_(None),
                    Deal.outcome == StageOutcome.WON,
                )
            )
        ).scalars():
            won[deal.account_id].append(deal)
    recorder_ids = {r.recorded_by_id for r in referrals if r.recorded_by_id}
    names = (
        dict((await db.execute(select(User.id, User.name).where(User.id.in_(recorder_ids)))).all())
        if recorder_ids
        else {}
    )
    views = []
    for r in referrals:
        referred = by_domain.get(r.referred_domain) if r.referred_domain else None
        view = ReferralView(
            referral=r,
            referrer=referrers.get(r.referrer_account_id) if r.referrer_account_id else None,
            referred=referred,
            recorded_by=names.get(r.recorded_by_id) if r.recorded_by_id else None,
        )
        since = datetime.combine(r.received_on, time.min, tzinfo=UTC)
        for deal in won[referred.id] if referred else []:
            if deal.closed_at is None or deal.closed_at < since:
                continue
            view.won_deals += 1
            if deal.value is None:
                view.unknown_value_deals += 1
            else:
                view.revenue[deal.currency] = (
                    view.revenue.get(deal.currency, Decimal(0)) + deal.value
                )
        views.append(view)
    return views


async def list_referrals(
    db: AsyncSession, *, user: User, account_id: uuid.UUID | None = None, limit: int = 200
) -> list[ReferralView]:
    """Every referral the user may see, newest first. With an account: the referrals it gave,
    and the one that brought it in."""
    stmt = select(Referral)
    clause = _visible_referrals(user)
    if clause is not None:
        stmt = stmt.outerjoin(Account, Account.id == Referral.referrer_account_id).where(clause)
    if account_id is not None:
        domains = select(AccountDomain.domain).where(AccountDomain.account_id == account_id)
        primary = select(Account.primary_domain).where(Account.id == account_id)
        stmt = stmt.where(
            or_(
                Referral.referrer_account_id == account_id,
                Referral.referred_domain.in_(domains),
                Referral.referred_domain.in_(primary),
            )
        )
    stmt = stmt.order_by(Referral.received_on.desc(), Referral.created_at.desc()).limit(limit)
    return await _views(db, user, list((await db.execute(stmt)).scalars()))


async def get_referral(db: AsyncSession, *, user: User, referral_id: uuid.UUID) -> ReferralView:
    referral = await db.get(Referral, referral_id)
    if referral is None:
        raise NotFound("Referral not found.")
    if referral.referrer_account_id is not None:
        referrer = await db.get(Account, referral.referrer_account_id)
        if referrer is None or not access.can_see(user, referrer.owner_id):
            raise NotFound("Referral not found.")
    return (await _views(db, user, [referral]))[0]


@dataclass
class NewReferral:
    referred_company: str
    referred_domain: str | None = None
    referrer_account_id: uuid.UUID | None = None
    referrer_contact_id: uuid.UUID | None = None
    referrer_name: str | None = None
    relationship: str | None = None
    notes: str | None = None
    received_on: date | None = None


async def create_referral(db: AsyncSession, *, user: User, data: NewReferral) -> Referral:
    referrer = None
    contact = None
    if data.referrer_account_id is not None:
        referrer = await db.get(Account, data.referrer_account_id)
        if (
            referrer is None
            or referrer.deleted_at is not None
            or not access.can_see(user, referrer.owner_id)
        ):
            raise NotFound("Account not found.")
    if data.referrer_contact_id is not None:
        contact = await db.get(Contact, data.referrer_contact_id)
        if (
            contact is None
            or contact.deleted_at is not None
            or (referrer is not None and contact.account_id != referrer.id)
        ):
            raise ValidationFailed("That person is not at the referring company.")
    name = (data.referrer_name or "").strip()
    if not name:
        parts = [contact.name if contact else None, referrer.name if referrer else None]
        name = ", ".join(p for p in parts if p)
    if not name:
        raise ValidationFailed("Say who made the referral.", code="referrer_required")
    when = data.received_on or _today()
    if when > _today():
        raise ValidationFailed("A referral cannot be from the future.")
    company = data.referred_company.strip()
    if not company:
        raise ValidationFailed("Name the company that was referred.")
    referral = Referral(
        referrer_account_id=referrer.id if referrer else None,
        referrer_contact_id=contact.id if contact else None,
        referrer_name=name[:200],
        relationship=(data.relationship or "").strip()[:120] or None,
        referred_company=company[:300],
        referred_domain=clean_domain(data.referred_domain),
        notes=(data.notes or "").strip() or None,
        received_on=when,
        recorded_by_id=user.id,
    )
    db.add(referral)
    await db.flush()
    if referrer is not None:
        timeline.add(
            db,
            account_id=referrer.id,
            event_type="referral.given",
            summary=f"Referred {referral.referred_company} to Verkies"
            + (f" ({contact.name})" if contact else "")
            + ".",
            actor_id=user.id,
            ref_table="referrals",
            ref_id=referral.id,
        )
    audit.record(
        db,
        action="referral.created",
        object_table="referrals",
        object_id=referral.id,
        user_id=user.id,
        source=AuditSource.API,
        new_value={
            "referrer_account_id": str(referrer.id) if referrer else None,
            "referrer_name": referral.referrer_name,
            "referred_company": referral.referred_company,
            "referred_domain": referral.referred_domain,
            "received_on": when.isoformat(),
        },
    )
    await db.commit()
    return referral


EDITABLE = ("status", "notes", "relationship", "referred_domain", "referred_company")


async def update_referral(
    db: AsyncSession, *, user: User, referral_id: uuid.UUID, changes: dict[str, Any]
) -> None:
    referral = (await get_referral(db, user=user, referral_id=referral_id)).referral
    if "referred_domain" in changes:
        changes["referred_domain"] = clean_domain(changes["referred_domain"])
    for key in ("notes", "relationship"):
        if key in changes:
            changes[key] = (changes[key] or "").strip() or None
    if "referred_company" in changes:
        changes["referred_company"] = (changes["referred_company"] or "").strip()[:300]
        if not changes["referred_company"]:
            raise ValidationFailed("Name the company that was referred.")
    changed = {k: v for k, v in changes.items() if k in EDITABLE and getattr(referral, k) != v}
    if not changed:
        return
    old = {k: getattr(referral, k) for k in changed}
    for key, value in changed.items():
        setattr(referral, key, value)
    audit.record(
        db,
        action="referral.updated",
        object_table="referrals",
        object_id=referral.id,
        user_id=user.id,
        source=AuditSource.API,
        old_value={k: v.value if isinstance(v, ReferralStatus) else v for k, v in old.items()},
        new_value={k: v.value if isinstance(v, ReferralStatus) else v for k, v in changed.items()},
    )
    await db.commit()
