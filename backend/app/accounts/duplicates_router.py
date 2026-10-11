"""/account-duplicates and /accounts/{id}/merge: review suggested duplicates, mark a pair as
different companies, or merge one account into another (§16, slice 2.6)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from app.accounts import merge, service
from app.accounts.schemas import AccountSummaryOut
from app.auth.deps import DbSession, require_permission
from app.auth.models import User

router = APIRouter(tags=["accounts"])

Merger = Annotated[User, Depends(require_permission("accounts.merge"))]


class DuplicatePairOut(BaseModel):
    account_a: AccountSummaryOut
    account_b: AccountSummaryOut
    reasons: list[str]
    similarity: float | None


class DismissIn(BaseModel):
    account_a_id: uuid.UUID
    account_b_id: uuid.UUID
    reason: str | None = Field(default=None, max_length=500)


class MergeIn(BaseModel):
    merge_id: uuid.UUID
    reason: str = Field(min_length=3, max_length=500)


class MergeOut(BaseModel):
    account_id: uuid.UUID
    retired_id: uuid.UUID
    moved: dict[str, int]
    filled: list[str]


@router.get("/account-duplicates")
async def list_duplicates(
    user: Merger, db: DbSession, limit: Annotated[int, Query(ge=1, le=200)] = 50
) -> list[DuplicatePairOut]:
    pairs = await merge.find_duplicates(db, user=user, limit=limit)
    accounts = [p.a for p in pairs] + [p.b for p in pairs]
    names = await service.user_names(db, {a.owner_id for a in accounts if a.owner_id})
    open_tasks = await service.count_open_tasks(db, [a.id for a in accounts])
    return [
        DuplicatePairOut(
            account_a=AccountSummaryOut.of(p.a, names, open_tasks.get(p.a.id, 0)),
            account_b=AccountSummaryOut.of(p.b, names, open_tasks.get(p.b.id, 0)),
            reasons=p.reasons,
            similarity=p.similarity,
        )
        for p in pairs
    ]


@router.post("/account-duplicates/dismiss", status_code=204)
async def dismiss_duplicate(body: DismissIn, user: Merger, db: DbSession) -> None:
    await merge.dismiss(
        db, user=user, first_id=body.account_a_id, second_id=body.account_b_id, reason=body.reason
    )


@router.post("/accounts/{account_id}/merge")
async def merge_account(
    account_id: uuid.UUID, body: MergeIn, user: Merger, db: DbSession
) -> MergeOut:
    """Merge `merge_id` into this account. The other account is retired, not deleted."""
    result = await merge.merge(
        db, user=user, keep_id=account_id, merge_id=body.merge_id, reason=body.reason
    )
    return MergeOut(
        account_id=result.kept.id,
        retired_id=result.retired_id,
        moved=result.moved,
        filled=result.filled,
    )
