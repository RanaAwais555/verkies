"""/outreach: templates, sequences, enrolling a contact, and the daily queue (slice 3.5)."""

import uuid
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.auth.deps import AppSettings, DbSession, require_permission
from app.auth.models import User
from app.core.enums import CallOutcome, OutreachChannel, StepOutcome
from app.mail.router import Dns, Providers
from app.outreach import service
from app.outreach.models import Enrollment, EnrollmentStep, OutreachTemplate, Sequence, SequenceStep

router = APIRouter(prefix="/outreach", tags=["outreach"])

Member = Annotated[User, Depends(require_permission("accounts.read", "accounts.read_own"))]


class VariableOut(BaseModel):
    key: str
    meaning: str


@router.get("/variables")
async def variables(user: Member) -> list[VariableOut]:
    return [VariableOut(key=k, meaning=v) for k, v in service.VARIABLES.items()]


# --- templates ---------------------------------------------------------------------------------


class TemplateOut(BaseModel):
    id: uuid.UUID
    name: str
    channel: str
    subject: str | None
    body: str
    service_id: uuid.UUID | None
    industry: str | None
    signal: str | None
    is_active: bool

    @classmethod
    def of(cls, t: OutreachTemplate) -> "TemplateOut":
        return cls(
            id=t.id,
            name=t.name,
            channel=t.channel.value,
            subject=t.subject,
            body=t.body,
            service_id=t.service_id,
            industry=t.industry,
            signal=t.signal,
            is_active=t.is_active,
        )


class TemplateIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    channel: OutreachChannel
    # Email only. Leave empty on a follow-up to reply in the sequence's thread.
    subject: str | None = Field(default=None, max_length=300)
    body: str = Field(min_length=1, max_length=10000)
    service_id: uuid.UUID | None = None
    industry: str | None = Field(default=None, max_length=120)
    signal: str | None = Field(default=None, max_length=60)
    is_active: bool = True


@router.get("/templates")
async def list_templates(user: Member, db: DbSession) -> list[TemplateOut]:
    rows = await db.execute(
        select(OutreachTemplate).order_by(OutreachTemplate.channel, OutreachTemplate.name)
    )
    return [TemplateOut.of(t) for t in rows.scalars()]


@router.post("/templates", status_code=201)
async def create_template(body: TemplateIn, user: Member, db: DbSession) -> TemplateOut:
    data = body.model_dump()
    if body.channel is not OutreachChannel.EMAIL:
        data["subject"] = None
    template = await service.save_template(db, user=user, template_id=None, data=data)
    await db.commit()
    return TemplateOut.of(template)


@router.put("/templates/{template_id}")
async def update_template(
    template_id: uuid.UUID, body: TemplateIn, user: Member, db: DbSession
) -> TemplateOut:
    data = body.model_dump()
    if body.channel is not OutreachChannel.EMAIL:
        data["subject"] = None
    template = await service.save_template(db, user=user, template_id=template_id, data=data)
    await db.commit()
    return TemplateOut.of(template)


# --- sequences ---------------------------------------------------------------------------------


class StepOut(BaseModel):
    id: uuid.UUID
    position: int
    channel: str
    delay_days: int
    template_id: uuid.UUID | None
    instructions: str | None


class SequenceOut(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    is_active: bool
    steps: list[StepOut]


def _sequence_out(sequence: Sequence, steps: list[SequenceStep]) -> SequenceOut:
    return SequenceOut(
        id=sequence.id,
        name=sequence.name,
        description=sequence.description,
        is_active=sequence.is_active,
        steps=[
            StepOut(
                id=s.id,
                position=s.position,
                channel=s.channel.value,
                delay_days=s.delay_days,
                template_id=s.template_id,
                instructions=s.instructions,
            )
            for s in steps
        ],
    )


class StepIn(BaseModel):
    channel: OutreachChannel
    delay_days: int = Field(ge=0, le=90)
    template_id: uuid.UUID | None = None
    instructions: str | None = Field(default=None, max_length=2000)


class SequenceIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    is_active: bool = True
    steps: list[StepIn] = Field(min_length=1, max_length=20)


@router.get("/sequences")
async def list_sequences(user: Member, db: DbSession) -> list[SequenceOut]:
    found = (
        await db.execute(select(Sequence).order_by(Sequence.is_active.desc(), Sequence.name))
    ).scalars()
    return [_sequence_out(s, await service.steps_of(db, s.id)) for s in found]


async def _save(
    db: DbSession, user: User, sequence_id: uuid.UUID | None, body: SequenceIn
) -> SequenceOut:
    sequence = await service.save_sequence(
        db,
        user=user,
        sequence_id=sequence_id,
        name=body.name,
        description=body.description,
        is_active=body.is_active,
        steps=[service.StepInput(**s.model_dump()) for s in body.steps],
    )
    await db.commit()
    return _sequence_out(sequence, await service.steps_of(db, sequence.id))


@router.post("/sequences", status_code=201)
async def create_sequence(body: SequenceIn, user: Member, db: DbSession) -> SequenceOut:
    return await _save(db, user, None, body)


@router.put("/sequences/{sequence_id}")
async def update_sequence(
    sequence_id: uuid.UUID, body: SequenceIn, user: Member, db: DbSession
) -> SequenceOut:
    return await _save(db, user, sequence_id, body)


class DraftOut(BaseModel):
    channel: str
    subject: str | None
    body: str
    missing: list[str]
    reply_to_id: uuid.UUID | None


def _draft_out(d: service.Draft) -> DraftOut:
    return DraftOut(
        channel=d.channel.value,
        subject=d.subject,
        body=d.body,
        missing=d.missing,
        reply_to_id=d.reply_to_id,
    )


class PreviewStep(BaseModel):
    position: int
    channel: str
    delay_days: int
    due_at: datetime
    draft: DraftOut


class PreviewOut(BaseModel):
    sequence: str
    steps: list[PreviewStep]


@router.get("/sequences/{sequence_id}/preview")
async def preview(
    sequence_id: uuid.UUID, contact_id: uuid.UUID, user: Member, db: DbSession
) -> PreviewOut:
    sequence, steps = await service.preview(
        db, user=user, sequence_id=sequence_id, contact_id=contact_id
    )
    return PreviewOut(
        sequence=sequence.name,
        steps=[
            PreviewStep(
                position=s.position,
                channel=s.channel.value,
                delay_days=s.delay_days,
                due_at=due,
                draft=_draft_out(d),
            )
            for s, d, due in steps
        ],
    )


# --- enrollments -------------------------------------------------------------------------------


class HistoryOut(BaseModel):
    position: int
    channel: str
    outcome: str
    note: str | None
    done_at: datetime


class EnrollmentOut(BaseModel):
    id: uuid.UUID
    sequence_id: uuid.UUID
    sequence_name: str
    contact_id: uuid.UUID
    account_id: uuid.UUID
    owner_id: uuid.UUID
    status: str
    stop_reason: str | None
    next_position: int
    total_steps: int
    next_due_at: datetime | None
    approved_at: datetime | None
    created_at: datetime
    history: list[HistoryOut]


def _enrollment_out(
    e: Enrollment, sequence: Sequence, total: int, history: list[EnrollmentStep]
) -> EnrollmentOut:
    return EnrollmentOut(
        id=e.id,
        sequence_id=sequence.id,
        sequence_name=sequence.name,
        contact_id=e.contact_id,
        account_id=e.account_id,
        owner_id=e.owner_id,
        status=e.status.value,
        stop_reason=e.stop_reason,
        next_position=e.next_position,
        total_steps=total,
        next_due_at=e.next_due_at,
        approved_at=e.approved_at,
        created_at=e.created_at,
        history=[
            HistoryOut(
                position=h.position,
                channel=h.channel.value,
                outcome=h.outcome.value,
                note=h.note,
                done_at=h.done_at,
            )
            for h in history
        ],
    )


class EnrollIn(BaseModel):
    sequence_id: uuid.UUID
    contact_id: uuid.UUID


async def _one(db: DbSession, user: User, enrollment_id: uuid.UUID) -> EnrollmentOut:
    enrollment = await db.get(Enrollment, enrollment_id)
    assert enrollment is not None
    found = await service.enrollments_for(
        db, user=user, contact_id=enrollment.contact_id, account_id=None
    )
    return next(_enrollment_out(*f) for f in found if f[0].id == enrollment_id)


@router.post("/enrollments", status_code=201)
async def enroll(body: EnrollIn, user: Member, db: DbSession) -> EnrollmentOut:
    enrollment = await service.enroll(
        db, user=user, sequence_id=body.sequence_id, contact_id=body.contact_id
    )
    await db.commit()
    return await _one(db, user, enrollment.id)


@router.get("/enrollments")
async def list_enrollments(
    user: Member,
    db: DbSession,
    contact_id: uuid.UUID | None = None,
    account_id: uuid.UUID | None = None,
) -> list[EnrollmentOut]:
    found = await service.enrollments_for(
        db, user=user, contact_id=contact_id, account_id=account_id
    )
    await db.commit()  # any enrollment that should have stopped is now stopped
    return [_enrollment_out(*f) for f in found]


class StepIn2(BaseModel):
    action: Literal["email", "linkedin", "call", "skip"]
    subject: str | None = Field(default=None, max_length=300)
    body: str | None = Field(default=None, max_length=20000)
    outcome: Literal["sent", "already_connected", "wrong_person"] | None = None
    call_outcome: CallOutcome | None = None
    profile_url: str | None = Field(default=None, max_length=500)
    note: str | None = Field(default=None, max_length=2000)


@router.post("/enrollments/{enrollment_id}/steps")
async def do_step(
    enrollment_id: uuid.UUID,
    body: StepIn2,
    user: Member,
    db: DbSession,
    settings: AppSettings,
    providers: Providers,
    dns: Dns,
) -> EnrollmentOut:
    await service.do_step(
        db,
        user=user,
        enrollment_id=enrollment_id,
        data=service.StepAction(
            action=body.action,
            subject=body.subject,
            body=body.body,
            outcome=StepOutcome(body.outcome) if body.outcome else None,
            call_outcome=body.call_outcome,
            profile_url=body.profile_url,
            note=body.note,
        ),
        settings=settings,
        providers=providers,
        dns=dns,
    )
    await db.commit()
    return await _one(db, user, enrollment_id)


class StopIn(BaseModel):
    reason: str = Field(default="", max_length=200)


@router.post("/enrollments/{enrollment_id}/stop")
async def stop(
    enrollment_id: uuid.UUID, body: StopIn, user: Member, db: DbSession
) -> EnrollmentOut:
    await service.stop(db, user=user, enrollment_id=enrollment_id, reason=body.reason)
    await db.commit()
    return await _one(db, user, enrollment_id)


# --- the queue ---------------------------------------------------------------------------------


class QueueItemOut(BaseModel):
    enrollment_id: uuid.UUID
    sequence_name: str
    position: int
    total_steps: int
    channel: str
    due_at: datetime | None
    contact_id: uuid.UUID
    contact_name: str
    contact_title: str | None
    contact_email: str | None
    contact_phone: str | None
    account_id: uuid.UUID
    account_name: str
    priority_band: str | None
    draft: DraftOut
    linkedin_url: str | None
    linkedin_is_search: bool


class LinkedInUseOut(BaseModel):
    today: int
    this_week: int
    daily_limit: int
    weekly_limit: int
    blocked: str | None


class QueueOut(BaseModel):
    items: list[QueueItemOut]
    linkedin: LinkedInUseOut


@router.get("/queue")
async def queue(user: Member, db: DbSession, settings: AppSettings) -> QueueOut:
    items = await service.queue(db, user=user)
    use = await service.linkedin_use(db, user, settings)
    await db.commit()  # stops found while building the queue are kept
    return QueueOut(
        items=[
            QueueItemOut(
                enrollment_id=i.enrollment.id,
                sequence_name=i.sequence.name,
                position=i.step.position,
                total_steps=i.total_steps,
                channel=i.step.channel.value,
                due_at=i.enrollment.next_due_at,
                contact_id=i.contact.id,
                contact_name=i.contact.name,
                contact_title=i.contact.title,
                contact_email=i.contact.email,
                contact_phone=i.contact.phone,
                account_id=i.account.id,
                account_name=i.account.name,
                priority_band=i.account.priority_band.value if i.account.priority_band else None,
                draft=_draft_out(i.draft),
                linkedin_url=i.linkedin_url,
                linkedin_is_search=not i.contact.linkedin_url,
            )
            for i in items
        ],
        linkedin=LinkedInUseOut(
            today=use.today,
            this_week=use.this_week,
            daily_limit=use.daily_limit,
            weekly_limit=use.weekly_limit,
            blocked=use.blocked,
        ),
    )
