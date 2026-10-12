"""Won clients as similarity references (master context §11, §15; slice 5.4).

A client becomes a reference from the outcomes of the deals Verkies won with it: what was true
when each deal was won (industry, the service sold) and the problem the deal answered. Like a
reference project, a client is only compared when its profile is complete: the industry is known,
and so is a service or a problem. A prospect is never compared with its own account.
"""

import uuid
from collections import defaultdict

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounts.models import Account, AccountDomain
from app.catalogue.models import Service
from app.core.enums import StageOutcome
from app.crm.models import Opportunity
from app.deals.models import Deal
from app.learning.models import DealOutcome
from app.similarity.engine import ReferenceProfile


async def client_references(
    db: AsyncSession, *, exclude_domain: str | None, exclude_account: uuid.UUID | None
) -> list[ReferenceProfile]:
    rows = (
        await db.execute(
            select(DealOutcome, Account, Opportunity.problem, Service.key)
            .join(Account, Account.id == DealOutcome.account_id)
            .join(Deal, Deal.id == DealOutcome.deal_id)
            .outerjoin(Opportunity, Opportunity.id == Deal.opportunity_id)
            .outerjoin(Service, Service.id == DealOutcome.service_id)
            .where(
                DealOutcome.superseded_at.is_(None),
                DealOutcome.outcome == StageOutcome.WON,
                Account.deleted_at.is_(None),
                Account.merged_into_id.is_(None),
            )
            .order_by(DealOutcome.closed_at.desc())
        )
    ).all()
    if exclude_domain:
        own = select(AccountDomain.account_id).where(AccountDomain.domain == exclude_domain)
        excluded = set(
            (
                await db.execute(
                    select(Account.id).where(
                        or_(Account.primary_domain == exclude_domain, Account.id.in_(own))
                    )
                )
            ).scalars()
        )
    else:
        excluded = set()
    if exclude_account is not None:
        excluded.add(exclude_account)

    industry: dict[uuid.UUID, str | None] = {}
    names: dict[uuid.UUID, str] = {}
    problems: dict[uuid.UUID, list[str]] = defaultdict(list)
    services: dict[uuid.UUID, list[str]] = defaultdict(list)
    for outcome, account, problem, service_key in rows:
        if account.id in excluded:
            continue
        names[account.id] = account.name
        industry.setdefault(account.id, outcome.industry)  # the latest win's
        if problem and problem not in problems[account.id]:
            problems[account.id].append(problem)
        if service_key and service_key not in services[account.id]:
            services[account.id].append(service_key)
    return [
        ReferenceProfile(
            name=names[account_id],
            industry=industry[account_id],
            problem=" ".join(problems[account_id]) or None,
            service_keys=tuple(services[account_id]),
            profile_complete=bool(industry[account_id])
            and bool(problems[account_id] or services[account_id]),
            kind="client",
            ref_id=account_id,
        )
        for account_id in names
    ]
