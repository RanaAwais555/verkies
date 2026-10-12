"""/pipelines and /deals: pipeline configuration, the deal board, moves and the forecast
(slice 3.1)."""

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from app.auth.deps import DbSession, require_permission
from app.auth.models import User
from app.core.enums import LostReason
from app.deals import service
from app.deals.service import LOST_REASON_LABELS, DealView, NewDeal

router = APIRouter(tags=["deals"])

Member = Annotated[User, Depends(require_permission("accounts.read", "accounts.read_own"))]
Configurer = Annotated[User, Depends(require_permission("config.manage"))]


class StageOut(BaseModel):
    id: uuid.UUID
    key: str
    name: str
    position: int
    probability: float | None
    outcome: str


class PipelineOut(BaseModel):
    id: uuid.UUID
    key: str
    name: str
    kind: str
    stages: list[StageOut]


class LostReasonOut(BaseModel):
    key: str
    label: str


class PipelinesOut(BaseModel):
    pipelines: list[PipelineOut]
    lost_reasons: list[LostReasonOut]


class OwnerOut(BaseModel):
    id: uuid.UUID
    name: str | None


class NextTaskOut(BaseModel):
    id: uuid.UUID
    title: str
    due_at: datetime | None
    owner_name: str | None


class DealOut(BaseModel):
    id: uuid.UUID
    name: str
    account_id: uuid.UUID
    account_name: str
    account_domain: str | None
    priority_band: str | None
    opportunity_id: uuid.UUID | None
    opportunity_name: str | None
    pipeline_id: uuid.UUID
    pipeline_key: str
    stage_id: uuid.UUID
    stage_key: str
    stage_name: str
    outcome: str
    value: float | None
    currency: str
    probability: float | None
    probability_is_stage_default: bool
    weighted_value: float | None
    expected_close: date | None
    owner: OwnerOut | None
    next_task: NextTaskOut | None
    last_activity_at: datetime | None
    stage_entered_at: datetime
    days_in_stage: int
    closed_at: datetime | None
    lost_reason: str | None
    lost_note: str | None
    requires_attention: list[str]
    project_id: uuid.UUID | None = None
    created_at: datetime

    @classmethod
    def of(cls, v: DealView) -> "DealOut":
        d, stage = v.deal, v.stage
        probability = service.effective_probability(d, stage)
        weighted = service.weighted(d, stage)
        return cls(
            id=d.id,
            name=d.name,
            account_id=v.account.id,
            account_name=v.account.name,
            account_domain=v.account.primary_domain,
            priority_band=v.account.priority_band.value if v.account.priority_band else None,
            opportunity_id=d.opportunity_id,
            opportunity_name=v.opportunity_name,
            pipeline_id=v.pipeline.id,
            pipeline_key=v.pipeline.key,
            stage_id=stage.id,
            stage_key=stage.key,
            stage_name=stage.name,
            outcome=d.outcome.value,
            value=float(d.value) if d.value is not None else None,
            currency=d.currency,
            probability=float(probability) if probability is not None else None,
            probability_is_stage_default=d.probability is None,
            weighted_value=float(weighted) if weighted is not None else None,
            expected_close=d.expected_close,
            owner=OwnerOut(id=d.owner_id, name=v.owner_name) if d.owner_id else None,
            next_task=NextTaskOut(
                id=v.next_task.id,
                title=v.next_task.title,
                due_at=v.next_task.due_at,
                owner_name=v.next_task_owner_name,
            )
            if v.next_task
            else None,
            last_activity_at=v.last_activity_at,
            stage_entered_at=d.stage_entered_at,
            days_in_stage=max(0, (datetime.now(UTC) - d.stage_entered_at).days),
            closed_at=d.closed_at,
            lost_reason=d.lost_reason.value if d.lost_reason else None,
            lost_note=d.lost_note,
            requires_attention=v.attention,
            project_id=v.project_id,
            created_at=d.created_at,
        )


class CreateDeal(BaseModel):
    opportunity_id: uuid.UUID | None = None
    account_id: uuid.UUID | None = None
    pipeline_id: uuid.UUID | None = None
    name: str | None = Field(default=None, min_length=1, max_length=200)
    value: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    currency: str = Field(default="GBP", pattern=r"^[A-Za-z]{3}$")
    expected_close: date | None = None
    owner_id: uuid.UUID | None = None


class UpdateDeal(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    value: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    currency: str | None = Field(default=None, pattern=r"^[A-Za-z]{3}$")
    probability: Decimal | None = Field(default=None, ge=0, le=100)
    expected_close: date | None = None
    owner_id: uuid.UUID | None = None


class MoveDeal(BaseModel):
    stage_id: uuid.UUID
    lost_reason: LostReason | None = None
    lost_note: str | None = Field(default=None, max_length=2000)


class UpdateStage(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    probability: Decimal | None = Field(default=None, ge=0, le=100)


class MonthOut(BaseModel):
    month: str
    count: int
    value: float
    weighted: float


class ForecastOut(BaseModel):
    currency: str
    open_count: int
    open_value: float
    unknown_value_count: int
    weighted_value: float
    unweighted_count: int
    no_close_date_count: int
    won_count: int
    won_value: float
    won_unknown_value_count: int
    lost_count: int
    lost_value: float
    lost_unknown_value_count: int
    months: list[MonthOut]


@router.get("/pipelines")
async def list_pipelines(user: Member, db: DbSession) -> PipelinesOut:
    return PipelinesOut(
        pipelines=[
            PipelineOut(
                id=p.id,
                key=p.key,
                name=p.name,
                kind=p.kind.value,
                stages=[
                    StageOut(
                        id=s.id,
                        key=s.key,
                        name=s.name,
                        position=s.position,
                        probability=float(s.probability) if s.probability is not None else None,
                        outcome=s.outcome.value,
                    )
                    for s in stages
                ],
            )
            for p, stages in await service.pipelines(db)
        ],
        lost_reasons=[LostReasonOut(key=k.value, label=v) for k, v in LOST_REASON_LABELS.items()],
    )


@router.patch("/pipeline-stages/{stage_id}")
async def update_stage(
    stage_id: uuid.UUID, body: UpdateStage, user: Configurer, db: DbSession
) -> StageOut:
    """Rename a stage or change its default probability. Audited; deals keep their own overrides."""
    s = await service.update_stage(
        db, user=user, stage_id=stage_id, changes=body.model_dump(exclude_unset=True)
    )
    return StageOut(
        id=s.id,
        key=s.key,
        name=s.name,
        position=s.position,
        probability=float(s.probability) if s.probability is not None else None,
        outcome=s.outcome.value,
    )


@router.get("/deals")
async def list_deals(
    user: Member,
    db: DbSession,
    pipeline_id: uuid.UUID | None = None,
    account_id: uuid.UUID | None = None,
    owner: Literal["me", "unassigned"] | None = None,
    status: Literal["open", "won", "lost", "closed", "all"] = "open",
) -> list[DealOut]:
    views = await service.list_deals(
        db, user=user, pipeline_id=pipeline_id, account_id=account_id, owner=owner, status=status
    )
    return [DealOut.of(v) for v in views]


@router.get("/deals/forecast")
async def forecast(
    user: Member,
    db: DbSession,
    pipeline_id: uuid.UUID | None = None,
    year: Annotated[int | None, Query(ge=2000, le=2100)] = None,
) -> list[ForecastOut]:
    """Open pipeline (total, weighted, by expected-close month) and deals won and lost in `year`
    (this year by default), per currency. Unknown values and probabilities are counted, not
    zeroed."""
    found = await service.forecast(
        db, user=user, pipeline_id=pipeline_id, year=year or datetime.now(UTC).year
    )
    return [
        ForecastOut(
            currency=f.currency,
            open_count=f.open_count,
            open_value=float(f.open_value),
            unknown_value_count=f.unknown_value_count,
            weighted_value=float(f.weighted_value),
            unweighted_count=f.unweighted_count,
            no_close_date_count=f.no_close_date_count,
            won_count=f.won_count,
            won_value=float(f.won_value),
            won_unknown_value_count=f.won_unknown_value_count,
            lost_count=f.lost_count,
            lost_value=float(f.lost_value),
            lost_unknown_value_count=f.lost_unknown_value_count,
            months=[
                MonthOut(month=m, count=x.count, value=float(x.value), weighted=float(x.weighted))
                for m, x in sorted(f.months.items())
            ],
        )
        for f in found
    ]


@router.post("/deals", status_code=201)
async def create_deal(body: CreateDeal, user: Member, db: DbSession) -> DealOut:
    deal_id = await service.create_deal(db, user=user, data=NewDeal(**body.model_dump()))
    return DealOut.of(await service.get_deal(db, user=user, deal_id=deal_id))


@router.get("/deals/{deal_id}")
async def get_deal(deal_id: uuid.UUID, user: Member, db: DbSession) -> DealOut:
    return DealOut.of(await service.get_deal(db, user=user, deal_id=deal_id))


@router.patch("/deals/{deal_id}")
async def update_deal(deal_id: uuid.UUID, body: UpdateDeal, user: Member, db: DbSession) -> DealOut:
    await service.update_deal(
        db, user=user, deal_id=deal_id, changes=body.model_dump(exclude_unset=True)
    )
    return DealOut.of(await service.get_deal(db, user=user, deal_id=deal_id))


@router.post("/deals/{deal_id}/move")
async def move_deal(deal_id: uuid.UUID, body: MoveDeal, user: Member, db: DbSession) -> DealOut:
    await service.move_deal(
        db,
        user=user,
        deal_id=deal_id,
        stage_id=body.stage_id,
        lost_reason=body.lost_reason,
        lost_note=body.lost_note,
    )
    return DealOut.of(await service.get_deal(db, user=user, deal_id=deal_id))
