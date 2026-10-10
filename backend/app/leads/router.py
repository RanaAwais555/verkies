"""/leads: "find my next 20 leads" and plain-English search, each result with its reasons."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.accounts import service as accounts
from app.accounts.schemas import AccountSummaryOut
from app.auth.deps import DbSession, require_permission
from app.auth.models import User
from app.leads import ranking
from app.leads.interpret import MAX_LIMIT, Filters, interpret

router = APIRouter(prefix="/leads", tags=["leads"])

Member = Annotated[User, Depends(require_permission("accounts.read", "accounts.read_own"))]


class ReasonOut(BaseModel):
    kind: str
    text: str
    source_url: str | None = None


class RankedOut(BaseModel):
    rank: int
    account: AccountSummaryOut
    reasons: list[ReasonOut]
    scored_at: datetime | None


class UnderstoodOut(BaseModel):
    phrase: str
    meaning: str


class InterpretationOut(BaseModel):
    understood: list[UnderstoodOut]
    unsupported: list[UnderstoodOut]
    top_leads: bool
    limit: int


class SearchOut(BaseModel):
    query: str
    interpretation: InterpretationOut
    results: list[RankedOut]


async def _out(db: DbSession, ranked: list[ranking.Ranked]) -> list[RankedOut]:
    found = [r.account for r in ranked]
    names = await accounts.user_names(db, {a.owner_id for a in found if a.owner_id})
    open_tasks = await accounts.count_open_tasks(db, [a.id for a in found])
    return [
        RankedOut(
            rank=i,
            account=AccountSummaryOut.of(r.account, names, open_tasks.get(r.account.id, 0)),
            reasons=[
                ReasonOut(kind=x.kind, text=x.text, source_url=x.source_url) for x in r.reasons
            ],
            scored_at=r.scored_at,
        )
        for i, r in enumerate(ranked, start=1)
    ]


@router.get("/top")
async def top_leads(
    user: Member, db: DbSession, limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = 20
) -> list[RankedOut]:
    """The best available prospects, not the newest: open prospects, scored, not in the Reject
    band and not on the do-not-contact list, ranked by priority."""
    return await _out(
        db, await ranking.rank(db, user=user, filters=Filters(top_leads=True, limit=limit))
    )


@router.get("/search")
async def search(
    user: Member,
    db: DbSession,
    q: Annotated[str, Query(min_length=2, max_length=300)],
    limit: Annotated[int | None, Query(ge=1, le=MAX_LIMIT)] = None,
) -> SearchOut:
    """A plain-English request, the filters it was read as, and the ranked results."""
    meaning = interpret(q, await ranking.vocabulary(db))
    if limit is not None:
        meaning.filters.limit = limit
    results = await _out(db, await ranking.rank(db, user=user, filters=meaning.filters))
    return SearchOut(
        query=q,
        interpretation=InterpretationOut(
            understood=[
                UnderstoodOut(phrase=u.phrase, meaning=u.meaning) for u in meaning.understood
            ],
            unsupported=[
                UnderstoodOut(phrase=u.phrase, meaning=u.meaning) for u in meaning.unsupported
            ],
            top_leads=meaning.filters.top_leads,
            limit=meaning.filters.limit,
        ),
        results=results,
    )
