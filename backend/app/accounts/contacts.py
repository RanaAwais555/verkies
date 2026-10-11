"""Adding and editing contacts by hand (master context §12; slice 3.2).

A contact a person adds is sourced "manual": they are vouching for it, so it carries full
confidence but stays unverified until someone marks it verified. The suppression list
(SECURITY.md §6) is honoured: a suppressed address or domain cannot be added back.
"""

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounts import access
from app.accounts.models import Account, Contact, Suppression
from app.audit import service as audit
from app.auth.models import User
from app.core.enums import AuditSource, SuppressionKind
from app.core.errors import Conflict, NotFound, ValidationFailed
from app.crm import timeline

EDITABLE = (
    "name",
    "title",
    "department",
    "email",
    "phone",
    "linkedin_url",
    "decision_maker_role",
    "verification_status",
    "notes",
)


def _plain(value: Any) -> Any:
    return value.value if hasattr(value, "value") else value


def _clean(changes: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in changes.items():
        if key not in EDITABLE:
            continue
        if isinstance(value, str):
            value = value.strip() or None
        if key == "email" and value:
            value = value.lower()
        out[key] = value
    if "name" in out and not out["name"]:
        raise ValidationFailed("A contact needs a name.")
    return out


async def _visible_account(db: AsyncSession, user: User, account_id: uuid.UUID) -> Account:
    account = await db.get(Account, account_id)
    if (
        account is None
        or account.deleted_at is not None
        or not access.can_see(user, account.owner_id)
    ):
        raise NotFound("Account not found.")
    return account


async def _check_email(
    db: AsyncSession, account_id: uuid.UUID, email: str, ignore: uuid.UUID | None = None
) -> None:
    domain = email.rsplit("@", 1)[-1]
    suppressed = (
        await db.execute(
            select(Suppression.id).where(
                or_(
                    (Suppression.kind == SuppressionKind.EMAIL)
                    & (func.lower(Suppression.value) == email),
                    (Suppression.kind == SuppressionKind.DOMAIN)
                    & (func.lower(Suppression.value) == domain),
                )
            )
        )
    ).first()
    if suppressed is not None:
        raise ValidationFailed(
            "This address is on the suppression list, so it cannot be added.", code="suppressed"
        )
    stmt = select(Contact.id).where(
        Contact.account_id == account_id,
        Contact.deleted_at.is_(None),
        func.lower(Contact.email) == email,
    )
    if ignore is not None:
        stmt = stmt.where(Contact.id != ignore)
    existing = (await db.execute(stmt)).scalar_one_or_none()
    if existing is not None:
        raise Conflict(
            "Someone on this account already has that email.",
            code="duplicate_contact",
            details={"contact_id": str(existing)},
        )


async def add_contact(
    db: AsyncSession, *, user: User, account_id: uuid.UUID, data: dict[str, Any]
) -> Contact:
    account = await _visible_account(db, user, account_id)
    fields = {k: v for k, v in _clean(data).items() if v is not None}
    if not fields.get("name"):
        raise ValidationFailed("A contact needs a name.")
    if fields.get("email"):
        await _check_email(db, account.id, fields["email"])
    contact = Contact(
        account_id=account.id,
        source="manual",
        collected_at=datetime.now(UTC),
        confidence=Decimal("1.00"),
        **fields,
    )
    db.add(contact)
    await db.flush()
    role = f", {contact.title}" if contact.title else ""
    timeline.add(
        db,
        account_id=account.id,
        event_type="contact.added",
        summary=f"Contact added: {contact.name}{role}.",
        actor_id=user.id,
        ref_table="contacts",
        ref_id=contact.id,
    )
    audit.record(
        db,
        action="contact.created",
        object_table="contacts",
        object_id=contact.id,
        user_id=user.id,
        source=AuditSource.API,
        new_value={k: _plain(v) for k, v in fields.items()},
    )
    return contact


async def get_contact(db: AsyncSession, *, user: User, contact_id: uuid.UUID) -> Contact:
    contact = await db.get(Contact, contact_id)
    if contact is None or contact.deleted_at is not None:
        raise NotFound("Contact not found.")
    await _visible_account(db, user, contact.account_id)
    return contact


async def update_contact(
    db: AsyncSession, *, user: User, contact_id: uuid.UUID, changes: dict[str, Any]
) -> Contact:
    contact = await get_contact(db, user=user, contact_id=contact_id)
    fields = _clean(changes)
    if "verification_status" in fields and fields["verification_status"] is None:
        raise ValidationFailed("Say whether the contact is verified.")
    changed = {k: v for k, v in fields.items() if getattr(contact, k) != v}
    if not changed:
        return contact
    if changed.get("email"):
        await _check_email(db, contact.account_id, changed["email"], ignore=contact.id)
    old = {k: _plain(getattr(contact, k)) for k in changed}
    for key, value in changed.items():
        setattr(contact, key, value)
    audit.record(
        db,
        action="contact.updated",
        object_table="contacts",
        object_id=contact.id,
        user_id=user.id,
        source=AuditSource.API,
        old_value=old,
        new_value={k: _plain(v) for k, v in changed.items()},
    )
    return contact
