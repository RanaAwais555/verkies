"""Activities logged by hand and the relationship tracking read from them (master context §12;
slice 3.2).

A person logs a call, meeting, note or manual message after it happened. VROS never contacts
anyone itself: an activity is a record, not an action. Each one is tied to an account and
optionally a contact, an opportunity and a deal, appears on the account's timeline at the moment
it happened, and is audited. Activities are never edited; a correction is a new note.

Relationship tracking is computed from these records on every read, never stored, so it cannot
drift from them: first and latest interaction, how many there were, and whether the person has
replied since we last reached out.
"""

import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounts import access
from app.accounts.models import Account, Contact
from app.audit import service as audit
from app.auth.models import User
from app.core.enums import (
    ActivityChannel,
    ActivityDirection,
    ActivityKind,
    AuditSource,
    CallOutcome,
    TaskStatus,
)
from app.core.errors import NotFound, ValidationFailed
from app.crm import service as tasks
from app.crm import timeline
from app.crm.models import Activity, Opportunity, Task
from app.deals.models import Deal

# A logged activity has already happened; allow for clocks a little apart.
FUTURE_SLACK = timedelta(minutes=5)
SUMMARY_ON_TIMELINE = 280

ResponseStatus = Literal["not_contacted", "no_reply", "awaiting_reply", "replied"]
MessageChannel = Literal["email", "linkedin", "whatsapp", "other"]

MESSAGE_CHANNELS: dict[str, ActivityChannel] = {
    "email": ActivityChannel.EMAIL,
    "linkedin": ActivityChannel.LINKEDIN,
    "whatsapp": ActivityChannel.WHATSAPP,
    "other": ActivityChannel.MANUAL,
}
CHANNEL_LABELS = {
    ActivityChannel.EMAIL: "Email",
    ActivityChannel.LINKEDIN: "LinkedIn message",
    ActivityChannel.WHATSAPP: "WhatsApp message",
    ActivityChannel.MANUAL: "Message",
}
CALL_OUTCOME_LABELS = {
    CallOutcome.CONNECTED: "connected",
    CallOutcome.NO_ANSWER: "no answer",
    CallOutcome.VOICEMAIL: "left a voicemail",
}
REPLIES = (ActivityDirection.INBOUND, ActivityDirection.CONVERSATION)


def _now() -> datetime:
    return datetime.now(UTC)


# --- relationship tracking ---------------------------------------------------------------------


@dataclass(frozen=True)
class Relationship:
    first_interaction_at: datetime | None
    latest_interaction_at: datetime | None
    interactions: int
    last_reply_at: datetime | None
    attempts_since_reply: int  # outbound messages and unanswered calls since the last reply
    response_status: ResponseStatus


def relationship(touches: Iterable[tuple[datetime, ActivityDirection]]) -> Relationship:
    """Fold a person's (or an account's) activities into its relationship status.

    Notes are internal and are not interactions. A reply is an inbound message or a conversation
    (a connected call or a meeting); everything else outbound is an attempt. When an attempt and
    a reply share a timestamp, the reply is taken as the later of the two.
    """
    ordered = sorted(
        (t for t in touches if t[1] is not ActivityDirection.INTERNAL),
        key=lambda t: (t[0], t[1] in REPLIES),
    )
    if not ordered:
        return Relationship(None, None, 0, None, 0, "not_contacted")
    last_reply_at = None
    attempts = 0
    for occurred_at, direction in ordered:
        if direction in REPLIES:
            last_reply_at = occurred_at
            attempts = 0
        else:
            attempts += 1
    status: ResponseStatus
    if last_reply_at is None:
        status = "no_reply"
    elif attempts:
        status = "awaiting_reply"
    else:
        status = "replied"
    return Relationship(
        first_interaction_at=ordered[0][0],
        latest_interaction_at=ordered[-1][0],
        interactions=len(ordered),
        last_reply_at=last_reply_at,
        attempts_since_reply=attempts,
        response_status=status,
    )


async def contact_relationships(
    db: AsyncSession, contact_ids: list[uuid.UUID]
) -> dict[uuid.UUID, Relationship]:
    touches: dict[uuid.UUID, list[tuple[datetime, ActivityDirection]]] = {
        c: [] for c in contact_ids
    }
    if contact_ids:
        rows = await db.execute(
            select(Activity.contact_id, Activity.occurred_at, Activity.direction).where(
                Activity.contact_id.in_(contact_ids)
            )
        )
        for contact_id, occurred_at, direction in rows.all():
            if contact_id is not None:
                touches[contact_id].append((occurred_at, direction))
    return {c: relationship(t) for c, t in touches.items()}


async def account_relationship(db: AsyncSession, account_id: uuid.UUID) -> Relationship:
    rows = await db.execute(
        select(Activity.occurred_at, Activity.direction).where(Activity.account_id == account_id)
    )
    return relationship((o, d) for o, d in rows.all())


# --- last touch (read by the follow-up engine and the deal board) ------------------------------


async def latest_touch(
    db: AsyncSession, column: Any, ids: list[uuid.UUID]
) -> dict[uuid.UUID, datetime]:
    """The latest logged activity or completed task per opportunity or deal.

    `column` is `"opportunity_id"` or `"deal_id"`; both tables carry it.
    """
    if not ids:
        return {}
    found: dict[uuid.UUID, datetime] = {}
    activity_col = getattr(Activity, column)
    task_col = getattr(Task, column)
    activity_rows = await db.execute(
        select(activity_col, func.max(Activity.occurred_at))
        .where(activity_col.in_(ids))
        .group_by(activity_col)
    )
    task_rows = await db.execute(
        select(task_col, func.max(Task.completed_at))
        .where(
            task_col.in_(ids),
            Task.deleted_at.is_(None),
            Task.status == TaskStatus.DONE,
            Task.completed_at.is_not(None),
        )
        .group_by(task_col)
    )
    for key, at in [*activity_rows.all(), *task_rows.all()]:
        if at is not None and (key not in found or at > found[key]):
            found[key] = at
    return found


# --- logging -----------------------------------------------------------------------------------


@dataclass
class FollowUp:
    title: str
    due_at: datetime
    owner_id: uuid.UUID | None = None


@dataclass
class NewActivity:
    account_id: uuid.UUID
    kind: ActivityKind
    summary: str
    occurred_at: datetime | None = None
    contact_id: uuid.UUID | None = None
    opportunity_id: uuid.UUID | None = None
    deal_id: uuid.UUID | None = None
    call_outcome: CallOutcome | None = None
    message_channel: MessageChannel | None = None
    received: bool = False  # a message they sent us, rather than one we sent
    follow_up: FollowUp | None = None


def classify(data: NewActivity) -> tuple[ActivityChannel, ActivityDirection]:
    """The channel and direction a kind of activity implies, after checking it carries the
    detail that kind needs."""
    if data.kind is not ActivityKind.CALL and data.call_outcome is not None:
        raise ValidationFailed("Only a call has an outcome.")
    if data.kind is not ActivityKind.MESSAGE and (data.message_channel or data.received):
        raise ValidationFailed("Only a message has a channel and a sender.")
    if data.kind is ActivityKind.CALL:
        if data.call_outcome is None:
            raise ValidationFailed("Say how the call went.", code="call_outcome_required")
        connected = data.call_outcome is CallOutcome.CONNECTED
        return ActivityChannel.CALL, (
            ActivityDirection.CONVERSATION if connected else ActivityDirection.OUTBOUND
        )
    if data.kind is ActivityKind.MEETING:
        return ActivityChannel.MEETING, ActivityDirection.CONVERSATION
    if data.kind is ActivityKind.MESSAGE:
        if data.message_channel is None:
            raise ValidationFailed(
                "Say where the message was sent.", code="message_channel_required"
            )
        return MESSAGE_CHANNELS[data.message_channel], (
            ActivityDirection.INBOUND if data.received else ActivityDirection.OUTBOUND
        )
    return ActivityChannel.MANUAL, ActivityDirection.INTERNAL


def _headline(data: NewActivity, channel: ActivityChannel, contact: Contact | None) -> str:
    who = contact.name if contact else None
    if data.kind is ActivityKind.CALL:
        outcome = CALL_OUTCOME_LABELS[data.call_outcome]  # type: ignore[index]
        return f"Call{f' with {who}' if who else ''}, {outcome}"
    if data.kind is ActivityKind.MEETING:
        return f"Meeting{f' with {who}' if who else ''}"
    if data.kind is ActivityKind.MESSAGE:
        label = CHANNEL_LABELS[channel]
        if who:
            return f"{label} {'from' if data.received else 'to'} {who}"
        return f"{label} {'received' if data.received else 'sent'}"
    return f"Note{f' about {who}' if who else ''}"


def _clip(text: str, limit: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


async def log_activity(db: AsyncSession, *, user: User, data: NewActivity) -> Activity:
    """Record an activity, put it on the timeline and, if asked, schedule the follow-up task.

    The caller commits.
    """
    summary = data.summary.strip()
    if not summary:
        raise ValidationFailed("Say what happened.")
    now = _now()
    occurred_at = data.occurred_at or now
    if occurred_at.tzinfo is None:
        occurred_at = occurred_at.replace(tzinfo=UTC)
    if occurred_at > now + FUTURE_SLACK:
        raise ValidationFailed(
            "That time is in the future. Plan it as a task instead.", code="occurred_in_future"
        )
    channel, direction = classify(data)

    account = await db.get(Account, data.account_id)
    if (
        account is None
        or account.deleted_at is not None
        or not access.can_see(user, account.owner_id)
    ):
        raise NotFound("Account not found.")
    contact = None
    if data.contact_id is not None:
        contact = await db.get(Contact, data.contact_id)
        if contact is None or contact.deleted_at is not None or contact.account_id != account.id:
            raise ValidationFailed("That contact is not on this account.")
    opportunity_id = data.opportunity_id
    if data.deal_id is not None:
        deal = await db.get(Deal, data.deal_id)
        if deal is None or deal.deleted_at is not None or deal.account_id != account.id:
            raise ValidationFailed("That deal is not on this account.")
        if opportunity_id is not None and opportunity_id != deal.opportunity_id:
            raise ValidationFailed("That deal belongs to a different opportunity.")
        opportunity_id = deal.opportunity_id
    opportunity = None
    if opportunity_id is not None:
        opportunity = await db.get(Opportunity, opportunity_id)
        if (
            opportunity is None
            or opportunity.deleted_at is not None
            or opportunity.account_id != account.id
        ):
            raise ValidationFailed("That opportunity is not on this account.")

    payload: dict[str, Any] = {}
    if data.call_outcome is not None:
        payload["call_outcome"] = data.call_outcome.value
    activity = Activity(
        account_id=account.id,
        contact_id=contact.id if contact else None,
        lead_id=opportunity.lead_id if opportunity else None,
        opportunity_id=opportunity.id if opportunity else None,
        deal_id=data.deal_id,
        channel=channel,
        direction=direction,
        activity_type=data.kind.value,
        occurred_at=occurred_at,
        actor_id=user.id,
        summary=summary,
        payload=payload,
    )
    db.add(activity)
    await db.flush()
    if account.last_activity_at is None or occurred_at > account.last_activity_at:
        account.last_activity_at = occurred_at

    timeline.add(
        db,
        account_id=account.id,
        event_type=f"activity.{data.kind.value}",
        summary=f"{_headline(data, channel, contact)}: {_clip(summary, SUMMARY_ON_TIMELINE)}",
        actor_id=user.id,
        ref_table="activities",
        ref_id=activity.id,
        occurred_at=occurred_at,
    )
    audit.record(
        db,
        action="activity.logged",
        object_table="activities",
        object_id=activity.id,
        user_id=user.id,
        source=AuditSource.API,
        new_value={
            "kind": data.kind.value,
            "channel": channel.value,
            "direction": direction.value,
            "occurred_at": occurred_at.isoformat(),
            "contact_id": str(contact.id) if contact else None,
            "opportunity_id": str(opportunity.id) if opportunity else None,
            "deal_id": str(data.deal_id) if data.deal_id else None,
            **payload,
        },
    )
    if data.follow_up is not None:
        await tasks.create_task(
            db,
            user=user,
            account_id=account.id,
            title=data.follow_up.title,
            owner_id=data.follow_up.owner_id or user.id,
            due_at=data.follow_up.due_at,
            opportunity_id=opportunity.id if opportunity else None,
            description=None,
            deal_id=data.deal_id,
            contact_id=contact.id if contact else None,
        )
    return activity


# --- reading -----------------------------------------------------------------------------------


@dataclass
class ActivityView:
    activity: Activity
    account_name: str
    contact_name: str | None
    actor_name: str | None


async def list_activities(
    db: AsyncSession,
    *,
    user: User,
    account_id: uuid.UUID | None = None,
    contact_id: uuid.UUID | None = None,
    opportunity_id: uuid.UUID | None = None,
    deal_id: uuid.UUID | None = None,
    limit: int = 100,
) -> list[ActivityView]:
    if not any((account_id, contact_id, opportunity_id, deal_id)):
        raise ValidationFailed("Say whose activities to list.")
    stmt = (
        select(Activity, Account.name)
        .join(Account, Account.id == Activity.account_id)
        .where(Account.deleted_at.is_(None))
    )
    clause = access.visible(user)
    if clause is not None:
        stmt = stmt.where(clause)
    for column, value in (
        (Activity.account_id, account_id),
        (Activity.contact_id, contact_id),
        (Activity.opportunity_id, opportunity_id),
        (Activity.deal_id, deal_id),
    ):
        if value is not None:
            stmt = stmt.where(column == value)
    stmt = stmt.order_by(Activity.occurred_at.desc(), Activity.id.desc()).limit(limit)
    rows = (await db.execute(stmt)).all()
    contact_ids = {a.contact_id for a, _ in rows if a.contact_id}
    actor_ids = {a.actor_id for a, _ in rows if a.actor_id}
    contacts = (
        dict(
            (
                await db.execute(
                    select(Contact.id, Contact.name).where(Contact.id.in_(contact_ids))
                )
            ).all()
        )
        if contact_ids
        else {}
    )
    actors = (
        dict((await db.execute(select(User.id, User.name).where(User.id.in_(actor_ids)))).all())
        if actor_ids
        else {}
    )
    return [
        ActivityView(
            activity=a,
            account_name=name,
            contact_name=contacts.get(a.contact_id) if a.contact_id else None,
            actor_name=actors.get(a.actor_id) if a.actor_id else None,
        )
        for a, name in rows
    ]
