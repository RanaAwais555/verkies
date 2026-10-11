"""Outreach: templates, sequences, enrolling a contact, and the daily queue (master context §12A,
§12B; slice 3.5).

Nothing is sent automatically. Enrolling a contact is a person approving every step of the
sequence; each step then waits in that person's queue until it is due, and they do it: send the
email (through the same pre-send checks as any email), send the LinkedIn note in their own browser
and record the outcome, or make the call. A sequence stops by itself when the contact replies, a
meeting is logged, a deal is opened, or the contact is suppressed (an opt-out or a bounce).
"""

import re
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import quote

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounts import access
from app.accounts.models import Account, Contact, Suppression
from app.audit import service as audit
from app.auth.models import User
from app.briefs.models import LeadBrief
from app.config import Settings
from app.core.enums import (
    AccountType,
    ActivityChannel,
    ActivityDirection,
    ActivityKind,
    AuditSource,
    CallOutcome,
    EnrollmentStatus,
    LinkedInConnectionStatus,
    OutreachChannel,
    StepOutcome,
    SuppressionKind,
)
from app.core.errors import Conflict, NotFound, PermissionDenied, ValidationFailed
from app.crm import timeline
from app.crm.activities import CALL_OUTCOME_LABELS, record_activity
from app.crm.models import Activity
from app.deals.models import Deal
from app.mail import service as mail
from app.mail.dns_check import DnsChecker, domain_of
from app.mail.models import EmailMessage
from app.mail.provider import ProviderFactory
from app.outreach.models import (
    Enrollment,
    EnrollmentStep,
    OutreachTemplate,
    Sequence,
    SequenceStep,
)

MANAGE = "outreach.manage"
VARIABLES = {
    "first_name": "The contact's first name",
    "name": "The contact's full name",
    "title": "The contact's job title",
    "company": "The account's name",
    "sender_name": "Your name, as on your mailbox",
    "why_now": "The lead brief's Why Now",
    "problem": "The lead brief's Problem Detected",
    "service": "The lead brief's Recommended Service",
    "similar_project": "The lead brief's Similar Verkies Project",
}
PLACEHOLDER = re.compile(r"\{([a-z_]+)\}")
# The lead brief section each brief variable reads.
BRIEF_SECTIONS = {
    "why_now": "why_now",
    "problem": "problem_detected",
    "service": "recommended_service",
    "similar_project": "similar_project",
}


def _now() -> datetime:
    return datetime.now(UTC)


# --- variables and rendering -------------------------------------------------------------------


def unknown_variables(text: str | None) -> list[str]:
    return sorted({m for m in PLACEHOLDER.findall(text or "") if m not in VARIABLES})


def render(text: str | None, values: dict[str, str | None]) -> tuple[str, list[str]]:
    """Fill {variables}. One with no value stays in the text, written as {name}, and is listed
    as missing: a person writes it in or removes it before sending. Nothing is made up."""
    missing: list[str] = []

    def fill(match: re.Match[str]) -> str:
        key = match.group(1)
        value = values.get(key)
        if key in VARIABLES and value:
            return value
        if key in VARIABLES and key not in missing:
            missing.append(key)
        return match.group(0)

    return PLACEHOLDER.sub(fill, text or ""), missing


def unfilled(text: str) -> list[str]:
    """Variables still in a text a person is about to send."""
    return sorted({m for m in PLACEHOLDER.findall(text) if m in VARIABLES})


async def variable_values(
    db: AsyncSession, contact: Contact, account: Account, sender_name: str
) -> dict[str, str | None]:
    brief = (
        await db.execute(
            select(LeadBrief.sections)
            .where(LeadBrief.account_id == account.id)
            .order_by(LeadBrief.generated_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none() or {}

    def section(name: str) -> str | None:
        claims = (brief.get(name) or {}).get("claims") or []
        text = " ".join(c.get("text", "").strip() for c in claims if c.get("text"))
        return text or None

    return {
        "first_name": contact.name.split()[0] if contact.name.strip() else None,
        "name": contact.name,
        "title": contact.title,
        "company": account.name,
        "sender_name": sender_name,
        **{key: section(name) for key, name in BRIEF_SECTIONS.items()},
    }


def linkedin_search_url(contact: Contact, account: Account) -> str:
    """A LinkedIn people search the person opens in their own browser. Nothing is fetched."""
    return "https://www.linkedin.com/search/results/people/?keywords=" + quote(
        f"{contact.name} {account.name}"
    )


# --- templates ---------------------------------------------------------------------------------


def _require_manager(user: User) -> None:
    if MANAGE not in user.permission_keys:
        raise PermissionDenied(
            "Only someone who manages outreach can change templates and sequences."
        )


def _check_text(*texts: str | None) -> None:
    bad = sorted({v for t in texts for v in unknown_variables(t)})
    if bad:
        raise ValidationFailed(
            f"Unknown variable: {', '.join('{' + b + '}' for b in bad)}.",
            code="unknown_variable",
            details={"known": sorted(VARIABLES)},
        )


async def save_template(
    db: AsyncSession, *, user: User, template_id: uuid.UUID | None, data: dict[str, Any]
) -> OutreachTemplate:
    _require_manager(user)
    _check_text(data.get("subject"), data["body"])
    if template_id is None:
        template = OutreachTemplate(created_by_id=user.id, **data)
        db.add(template)
    else:
        found = await db.get(OutreachTemplate, template_id)
        if found is None:
            raise NotFound("Template not found.")
        template = found
        for key, value in data.items():
            setattr(template, key, value)
    await db.flush()
    audit.record(
        db,
        action="outreach_template.saved",
        object_table="outreach_templates",
        object_id=template.id,
        user_id=user.id,
        source=AuditSource.API,
        new_value={
            k: (v.value if hasattr(v, "value") else str(v) if v else v) for k, v in data.items()
        },
    )
    return template


# --- sequences ---------------------------------------------------------------------------------


@dataclass
class StepInput:
    channel: OutreachChannel
    delay_days: int
    template_id: uuid.UUID | None = None
    instructions: str | None = None


async def steps_of(db: AsyncSession, sequence_id: uuid.UUID) -> list[SequenceStep]:
    return list(
        (
            await db.execute(
                select(SequenceStep)
                .where(SequenceStep.sequence_id == sequence_id)
                .order_by(SequenceStep.position)
            )
        ).scalars()
    )


async def save_sequence(
    db: AsyncSession,
    *,
    user: User,
    sequence_id: uuid.UUID | None,
    name: str,
    description: str | None,
    is_active: bool,
    steps: list[StepInput],
) -> Sequence:
    _require_manager(user)
    if not steps:
        raise ValidationFailed("A sequence needs at least one step.")
    for step in steps:
        if step.template_id is not None:
            template = await db.get(OutreachTemplate, step.template_id)
            if template is None or template.channel is not step.channel:
                raise ValidationFailed(f"That template is not a {step.channel.value} template.")
        elif step.channel is not OutreachChannel.CALL:
            raise ValidationFailed(f"An {step.channel.value} step needs a template.")
        _check_text(step.instructions)
    if sequence_id is None:
        sequence = Sequence(
            name=name.strip(), description=description, is_active=is_active, created_by_id=user.id
        )
        db.add(sequence)
        await db.flush()
    else:
        existing = await db.get(Sequence, sequence_id)
        if existing is None:
            raise NotFound("Sequence not found.")
        sequence = existing
        current = await steps_of(db, sequence.id)
        changed = [(s.channel, s.delay_days, s.template_id, s.instructions) for s in current] != [
            (s.channel, s.delay_days, s.template_id, s.instructions) for s in steps
        ]
        live = (
            await db.execute(
                select(func.count()).where(
                    Enrollment.sequence_id == sequence.id,
                    Enrollment.status == EnrollmentStatus.ACTIVE,
                )
            )
        ).scalar_one()
        if changed and live:
            raise Conflict(
                "People are going through this sequence, so its steps cannot change. "
                "Make a new one.",
                code="sequence_in_use",
            )
        sequence.name, sequence.description, sequence.is_active = (
            name.strip(),
            description,
            is_active,
        )
        if changed:
            used = (
                await db.execute(select(func.count()).where(Enrollment.sequence_id == sequence.id))
            ).scalar_one()
            if used:
                raise Conflict(
                    "This sequence has history, so its steps cannot change. Make a new one.",
                    code="sequence_in_use",
                )
            for old in current:
                await db.delete(old)
            await db.flush()
    if sequence_id is None or changed:
        for position, step in enumerate(steps):
            db.add(
                SequenceStep(
                    sequence_id=sequence.id,
                    position=position,
                    channel=step.channel,
                    delay_days=step.delay_days,
                    template_id=step.template_id,
                    instructions=step.instructions,
                )
            )
    await db.flush()
    audit.record(
        db,
        action="sequence.saved",
        object_table="sequences",
        object_id=sequence.id,
        user_id=user.id,
        source=AuditSource.API,
        new_value={
            "name": sequence.name,
            "is_active": is_active,
            "steps": [f"{s.channel.value}+{s.delay_days}d" for s in steps],
        },
    )
    return sequence


# --- drafting a step ---------------------------------------------------------------------------


@dataclass
class Draft:
    channel: OutreachChannel
    subject: str | None
    body: str
    missing: list[str] = field(default_factory=list)
    reply_to_id: uuid.UUID | None = None  # follow-up emails stay in the sequence's thread


async def _last_sent(db: AsyncSession, enrollment_id: uuid.UUID) -> EmailMessage | None:
    return (
        await db.execute(
            select(EmailMessage)
            .join(EnrollmentStep, EnrollmentStep.email_message_id == EmailMessage.id)
            .where(EnrollmentStep.enrollment_id == enrollment_id)
            .order_by(EnrollmentStep.done_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def draft_step(
    db: AsyncSession,
    *,
    step: SequenceStep,
    contact: Contact,
    account: Account,
    sender_name: str,
    enrollment_id: uuid.UUID | None = None,
    thread_subject: str | None = None,
) -> Draft:
    """A step as it would read for this contact. `thread_subject` is the subject an earlier email
    step would carry, so a preview shows a follow-up as the reply it will be."""
    values = await variable_values(db, contact, account, sender_name)
    template = await db.get(OutreachTemplate, step.template_id) if step.template_id else None
    subject, missing_subject = render(template.subject if template else None, values)
    body, missing_body = render(template.body if template else step.instructions, values)
    reply_to = None
    if step.channel is OutreachChannel.EMAIL and template is not None and not template.subject:
        previous = await _last_sent(db, enrollment_id) if enrollment_id else None
        if previous is not None:
            reply_to = previous.id
            subject = (
                previous.subject
                if previous.subject.lower().startswith("re:")
                else f"Re: {previous.subject}"
            )
        elif thread_subject:
            subject = (
                thread_subject
                if thread_subject.lower().startswith("re:")
                else f"Re: {thread_subject}"
            )
            missing_subject = unfilled(thread_subject)
        else:
            subject = ""
            missing_subject = ["subject"]
    missing = list(dict.fromkeys([*missing_subject, *missing_body]))
    return Draft(step.channel, subject or None, body, missing, reply_to)


# --- enrolling ---------------------------------------------------------------------------------


async def _visible(db: AsyncSession, user: User, contact_id: uuid.UUID) -> tuple[Contact, Account]:
    contact = await db.get(Contact, contact_id)
    if contact is None or contact.deleted_at is not None:
        raise NotFound("Contact not found.")
    account = await db.get(Account, contact.account_id)
    if (
        account is None
        or account.deleted_at is not None
        or not access.can_see(user, account.owner_id)
    ):
        raise NotFound("Contact not found.")
    return contact, account


async def suppression_reason(db: AsyncSession, contact: Contact, account: Account) -> str | None:
    email = (contact.email or "").strip().lower()
    conditions = [
        (Suppression.kind == SuppressionKind.ACCOUNT) & (Suppression.value == str(account.id)),
    ]
    if email:
        conditions += [
            (Suppression.kind == SuppressionKind.EMAIL) & (func.lower(Suppression.value) == email),
            (Suppression.kind == SuppressionKind.DOMAIN)
            & (func.lower(Suppression.value) == domain_of(email)),
        ]
    found = (await db.execute(select(Suppression.reason).where(or_(*conditions)))).first()
    return found[0] if found else None


async def sender_name(db: AsyncSession, user: User) -> str:
    mailbox = await mail.my_mailbox(db, user)
    return mailbox.display_name if mailbox else user.name


async def preview(
    db: AsyncSession, *, user: User, sequence_id: uuid.UUID, contact_id: uuid.UUID
) -> tuple[Sequence, list[tuple[SequenceStep, Draft, datetime]]]:
    """Every step as it would read for this contact, and when each would fall due: what a person
    reviews before approving the sequence."""
    contact, account = await _visible(db, user, contact_id)
    sequence = await db.get(Sequence, sequence_id)
    if sequence is None:
        raise NotFound("Sequence not found.")
    name = await sender_name(db, user)
    due = _now()
    out = []
    thread: str | None = None
    for step in await steps_of(db, sequence.id):
        due = due + timedelta(days=step.delay_days)
        draft = await draft_step(
            db, step=step, contact=contact, account=account, sender_name=name, thread_subject=thread
        )
        if step.channel is OutreachChannel.EMAIL and draft.subject:
            thread = thread or draft.subject
        out.append((step, draft, due))
    return sequence, out


async def enroll(
    db: AsyncSession, *, user: User, sequence_id: uuid.UUID, contact_id: uuid.UUID
) -> Enrollment:
    contact, account = await _visible(db, user, contact_id)
    sequence = await db.get(Sequence, sequence_id)
    if sequence is None or not sequence.is_active:
        raise NotFound("Sequence not found.")
    steps = await steps_of(db, sequence.id)
    if not steps:
        raise ValidationFailed("This sequence has no steps.")
    if account.account_type is AccountType.COMPETITOR:
        raise ValidationFailed(f"{account.name} is marked as a competitor.", code="competitor")
    reason = await suppression_reason(db, contact, account)
    if reason:
        raise ValidationFailed(
            f"{contact.name} is on the suppression list: {reason}", code="suppressed"
        )
    if any(s.channel is OutreachChannel.EMAIL for s in steps) and not contact.email:
        raise ValidationFailed(
            f"{contact.name} has no email address, and this sequence sends email."
        )
    live = (
        await db.execute(
            select(Enrollment.id).where(
                Enrollment.contact_id == contact.id, Enrollment.status == EnrollmentStatus.ACTIVE
            )
        )
    ).scalar_one_or_none()
    if live is not None:
        raise Conflict(
            f"{contact.name} is already in a sequence.",
            code="already_enrolled",
            details={"enrollment_id": str(live)},
        )
    now = _now()
    enrollment = Enrollment(
        sequence_id=sequence.id,
        contact_id=contact.id,
        account_id=account.id,
        owner_id=user.id,
        next_position=0,
        next_due_at=now + timedelta(days=steps[0].delay_days),
        approved_by_id=user.id,
        approved_at=now,
    )
    db.add(enrollment)
    await db.flush()
    timeline.add(
        db,
        account_id=account.id,
        event_type="outreach.enrolled",
        summary=f"{contact.name} enrolled in {sequence.name} ({len(steps)} steps), approved by "
        f"{user.name}.",
        actor_id=user.id,
        ref_table="enrollments",
        ref_id=enrollment.id,
    )
    audit.record(
        db,
        action="enrollment.approved",
        object_table="enrollments",
        object_id=enrollment.id,
        user_id=user.id,
        source=AuditSource.API,
        new_value={"sequence": sequence.name, "contact_id": str(contact.id)},
    )
    return enrollment


# --- stopping ----------------------------------------------------------------------------------


async def stop_reason(db: AsyncSession, enrollment: Enrollment) -> str | None:
    """Why this enrollment should stop now (§12B.4), or None. Read from the records, every time."""
    contact = await db.get(Contact, enrollment.contact_id)
    account = await db.get(Account, enrollment.account_id)
    if contact is None or contact.deleted_at is not None or account is None or account.deleted_at:
        return "The contact was removed"
    if await suppression_reason(db, contact, account):
        return "Suppressed (opted out, bounced or do-not-contact)"
    answered = (
        await db.execute(
            select(Activity.activity_type)
            .where(
                Activity.contact_id == contact.id,
                Activity.direction.in_((ActivityDirection.INBOUND, ActivityDirection.CONVERSATION)),
                Activity.occurred_at >= enrollment.created_at,
            )
            .order_by(Activity.occurred_at)
            .limit(1)
        )
    ).scalar_one_or_none()
    if answered == ActivityKind.MEETING.value:
        return "A meeting was logged"
    if answered is not None:
        return "They replied or spoke with you"
    deal = (
        await db.execute(
            select(Deal.id).where(
                Deal.account_id == account.id,
                Deal.deleted_at.is_(None),
                Deal.created_at >= enrollment.created_at,
            )
        )
    ).first()
    if deal is not None:
        return "A deal was opened"
    return None


async def _end(
    db: AsyncSession,
    enrollment: Enrollment,
    status: EnrollmentStatus,
    reason: str | None,
    actor_id: uuid.UUID | None,
) -> None:
    enrollment.status = status
    enrollment.stop_reason = reason
    enrollment.ended_at = _now()
    enrollment.next_due_at = None
    sequence = await db.get(Sequence, enrollment.sequence_id)
    contact = await db.get(Contact, enrollment.contact_id)
    what = (
        f"{contact.name if contact else 'Contact'} in {sequence.name if sequence else 'sequence'}"
    )
    timeline.add(
        db,
        account_id=enrollment.account_id,
        event_type=f"outreach.{status.value}",
        summary=f"Sequence finished: {what}."
        if status is EnrollmentStatus.COMPLETED
        else f"Sequence stopped: {what}. {reason}.",
        actor_id=actor_id,
        ref_table="enrollments",
        ref_id=enrollment.id,
    )


async def refresh(db: AsyncSession, enrollment: Enrollment) -> None:
    """Stop an active enrollment when the records say it should stop."""
    if enrollment.status is not EnrollmentStatus.ACTIVE:
        return
    reason = await stop_reason(db, enrollment)
    if reason:
        await _end(db, enrollment, EnrollmentStatus.STOPPED, reason, None)


async def stop(
    db: AsyncSession, *, user: User, enrollment_id: uuid.UUID, reason: str
) -> Enrollment:
    enrollment = await _owned(db, user, enrollment_id)
    if enrollment.status is not EnrollmentStatus.ACTIVE:
        raise Conflict("This sequence has already ended.")
    await _end(
        db, enrollment, EnrollmentStatus.STOPPED, reason.strip() or "Stopped by hand", user.id
    )
    return enrollment


# --- the queue ---------------------------------------------------------------------------------


@dataclass
class QueueItem:
    enrollment: Enrollment
    sequence: Sequence
    step: SequenceStep
    total_steps: int
    contact: Contact
    account: Account
    draft: Draft
    linkedin_url: str | None


@dataclass
class LinkedInUse:
    today: int
    this_week: int
    daily_limit: int
    weekly_limit: int

    @property
    def blocked(self) -> str | None:
        if self.today >= self.daily_limit:
            return f"You have sent your {self.daily_limit} LinkedIn notes for today."
        if self.this_week >= self.weekly_limit:
            return f"You have sent your {self.weekly_limit} LinkedIn notes for this week."
        return None


async def linkedin_use(db: AsyncSession, user: User, settings: Settings) -> LinkedInUse:
    now = _now()
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)

    async def count(since: datetime) -> int:
        return int(
            (
                await db.execute(
                    select(func.count()).where(
                        EnrollmentStep.done_by_id == user.id,
                        EnrollmentStep.channel == OutreachChannel.LINKEDIN,
                        EnrollmentStep.outcome == StepOutcome.SENT,
                        EnrollmentStep.done_at >= since,
                    )
                )
            ).scalar_one()
        )

    return LinkedInUse(
        await count(start_of_day),
        await count(now - timedelta(days=7)),
        settings.linkedin_daily_limit,
        settings.linkedin_weekly_limit,
    )


async def queue(db: AsyncSession, *, user: User) -> list[QueueItem]:
    """The person's steps due by the end of today, best prospects first."""
    end_of_day = _now().replace(hour=23, minute=59, second=59)
    rows = (
        await db.execute(
            select(Enrollment, Account)
            .join(Account, Account.id == Enrollment.account_id)
            .where(
                Enrollment.owner_id == user.id,
                Enrollment.status == EnrollmentStatus.ACTIVE,
                Enrollment.next_due_at <= end_of_day,
            )
            .order_by(Account.priority_score.desc().nulls_last(), Enrollment.next_due_at)
        )
    ).all()
    name = await sender_name(db, user)
    items = []
    for enrollment, account in rows:
        await refresh(db, enrollment)
        if enrollment.status is not EnrollmentStatus.ACTIVE:
            continue
        steps = await steps_of(db, enrollment.sequence_id)
        step = steps[enrollment.next_position]
        contact = await db.get(Contact, enrollment.contact_id)
        sequence = await db.get(Sequence, enrollment.sequence_id)
        assert contact is not None and sequence is not None
        draft = await draft_step(
            db,
            step=step,
            contact=contact,
            account=account,
            sender_name=name,
            enrollment_id=enrollment.id,
        )
        items.append(
            QueueItem(
                enrollment,
                sequence,
                step,
                len(steps),
                contact,
                account,
                draft,
                contact.linkedin_url or linkedin_search_url(contact, account),
            )
        )
    return items


# --- doing a step ------------------------------------------------------------------------------


async def _owned(db: AsyncSession, user: User, enrollment_id: uuid.UUID) -> Enrollment:
    enrollment = await db.get(Enrollment, enrollment_id)
    if enrollment is None:
        raise NotFound("Enrollment not found.")
    account = await db.get(Account, enrollment.account_id)
    if account is None or not access.can_see(user, account.owner_id):
        raise NotFound("Enrollment not found.")
    if enrollment.owner_id != user.id:
        raise PermissionDenied("Only the person who enrolled this contact works the sequence.")
    return enrollment


@dataclass
class StepAction:
    action: str  # "email", "linkedin", "call" or "skip"
    subject: str | None = None
    body: str | None = None
    outcome: StepOutcome | None = None  # LinkedIn: sent, already_connected or wrong_person
    call_outcome: CallOutcome | None = None
    profile_url: str | None = None
    note: str | None = None


async def do_step(
    db: AsyncSession,
    *,
    user: User,
    enrollment_id: uuid.UUID,
    data: StepAction,
    settings: Settings,
    providers: ProviderFactory,
    dns: DnsChecker,
) -> Enrollment:
    enrollment = await _owned(db, user, enrollment_id)
    await refresh(db, enrollment)
    if enrollment.status is not EnrollmentStatus.ACTIVE:
        await db.commit()
        raise Conflict(
            f"This sequence has ended: {enrollment.stop_reason or 'finished'}.", code="ended"
        )
    if enrollment.next_due_at and enrollment.next_due_at.date() > _now().date():
        raise Conflict(
            f"This step is not due until {enrollment.next_due_at.date().isoformat()}.",
            code="not_due",
        )
    steps = await steps_of(db, enrollment.sequence_id)
    step = steps[enrollment.next_position]
    contact = await db.get(Contact, enrollment.contact_id)
    account = await db.get(Account, enrollment.account_id)
    assert contact is not None and account is not None
    if data.action != "skip" and data.action != step.channel.value:
        raise ValidationFailed(f"This step is a {step.channel.value} step.")

    record = EnrollmentStep(
        enrollment_id=enrollment.id,
        step_id=step.id,
        position=step.position,
        channel=step.channel,
        outcome=StepOutcome.SKIPPED,
        note=data.note,
        done_by_id=user.id,
        done_at=_now(),
    )

    if data.action == "email":
        subject, body = (data.subject or "").strip(), (data.body or "").strip()
        left = unfilled(f"{subject}\n{body}")
        if left:
            raise ValidationFailed(
                "Fill in or remove " + ", ".join("{" + v + "}" for v in left) + " before sending.",
                code="unfilled_variables",
            )
        previous = await _last_sent(db, enrollment.id)
        message = await mail.send(
            db,
            user=user,
            draft=mail.Draft(
                contact_id=contact.id,
                subject=subject,
                body=body,
                reply_to_id=previous.id if previous else None,
            ),
            settings=settings,
            providers=providers,
            dns=dns,
        )
        record.outcome = StepOutcome.SENT
        record.email_message_id = message.id
        record.activity_id = message.activity_id

    elif data.action == "linkedin":
        if data.outcome not in (
            StepOutcome.SENT,
            StepOutcome.ALREADY_CONNECTED,
            StepOutcome.WRONG_PERSON,
        ):
            raise ValidationFailed("Say how the LinkedIn step went.")
        if data.profile_url:
            if not re.match(r"^https://([a-z]+\.)?linkedin\.com/", data.profile_url):
                raise ValidationFailed("That is not a LinkedIn profile link.")
            contact.linkedin_url = data.profile_url
        record.outcome = data.outcome
        if data.outcome is StepOutcome.SENT:
            blocked = (await linkedin_use(db, user, settings)).blocked
            if blocked:
                raise ValidationFailed(blocked, code="linkedin_limit")
            contact.linkedin_connection_status = LinkedInConnectionStatus.PENDING
            activity = await record_activity(
                db,
                actor_id=user.id,
                account=account,
                contact=contact,
                opportunity=None,
                deal_id=None,
                kind=ActivityKind.MESSAGE,
                channel=ActivityChannel.LINKEDIN,
                direction=ActivityDirection.OUTBOUND,
                occurred_at=record.done_at,
                summary=(data.body or "").strip() or "LinkedIn connection request sent.",
                headline=f"LinkedIn message to {contact.name}",
            )
            record.activity_id = activity.id
        elif data.outcome is StepOutcome.ALREADY_CONNECTED:
            contact.linkedin_connection_status = LinkedInConnectionStatus.CONNECTED

    elif data.action == "call":
        if data.call_outcome is None:
            raise ValidationFailed("Say how the call went.", code="call_outcome_required")
        connected = data.call_outcome is CallOutcome.CONNECTED
        activity = await record_activity(
            db,
            actor_id=user.id,
            account=account,
            contact=contact,
            opportunity=None,
            deal_id=None,
            kind=ActivityKind.CALL,
            channel=ActivityChannel.CALL,
            direction=ActivityDirection.CONVERSATION if connected else ActivityDirection.OUTBOUND,
            occurred_at=record.done_at,
            summary=(data.note or "").strip()
            or f"Sequence call: {CALL_OUTCOME_LABELS[data.call_outcome]}.",
            headline=f"Call with {contact.name}, {CALL_OUTCOME_LABELS[data.call_outcome]}",
            payload={"call_outcome": data.call_outcome.value},
        )
        record.outcome = StepOutcome.CALLED
        record.activity_id = activity.id

    db.add(record)
    await db.flush()
    audit.record(
        db,
        action="outreach.step",
        object_table="enrollments",
        object_id=enrollment.id,
        user_id=user.id,
        source=AuditSource.API,
        new_value={
            "position": step.position,
            "channel": step.channel.value,
            "outcome": record.outcome.value,
        },
    )

    if record.outcome is StepOutcome.WRONG_PERSON:
        await _end(db, enrollment, EnrollmentStatus.STOPPED, "Wrong person", user.id)
    elif enrollment.next_position + 1 >= len(steps):
        enrollment.next_position += 1
        await _end(db, enrollment, EnrollmentStatus.COMPLETED, None, user.id)
    else:
        enrollment.next_position += 1
        enrollment.next_due_at = record.done_at + timedelta(
            days=steps[enrollment.next_position].delay_days
        )
        # A connected call is a conversation: the sequence has done its job.
        await refresh(db, enrollment)
    return enrollment


# --- reading enrollments -----------------------------------------------------------------------


async def enrollments_for(
    db: AsyncSession, *, user: User, contact_id: uuid.UUID | None, account_id: uuid.UUID | None
) -> list[tuple[Enrollment, Sequence, int, list[EnrollmentStep]]]:
    if contact_id is None and account_id is None:
        raise ValidationFailed("Say whose sequences to list.")
    stmt = (
        select(Enrollment, Sequence)
        .join(Sequence, Sequence.id == Enrollment.sequence_id)
        .join(Account, Account.id == Enrollment.account_id)
    )
    clause = access.visible(user)
    if clause is not None:
        stmt = stmt.where(clause)
    if contact_id is not None:
        stmt = stmt.where(Enrollment.contact_id == contact_id)
    if account_id is not None:
        stmt = stmt.where(Enrollment.account_id == account_id)
    out = []
    for enrollment, sequence in (
        await db.execute(stmt.order_by(Enrollment.created_at.desc()))
    ).all():
        await refresh(db, enrollment)
        history = list(
            (
                await db.execute(
                    select(EnrollmentStep)
                    .where(EnrollmentStep.enrollment_id == enrollment.id)
                    .order_by(EnrollmentStep.done_at)
                )
            ).scalars()
        )
        out.append((enrollment, sequence, len(await steps_of(db, sequence.id)), history))
    return out
