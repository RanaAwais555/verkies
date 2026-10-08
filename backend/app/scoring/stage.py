"""Detect, qualify and score stages: load a run's evidence-backed facts, run the
deterministic engines, and store candidates, the qualification result and a score snapshot."""

import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import String, cast, delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from app.accounts.models import AccountDomain, Suppression
from app.catalogue.matching import Match, ServiceInfo, match_services
from app.catalogue.models import ReferenceProject, Service
from app.core.enums import SuppressionKind
from app.evidence.models import Observation
from app.intelligence.facts import Fact, Facts
from app.opportunities.detectors import Candidate, detect
from app.opportunities.models import (
    OpportunityCandidate,
    OpportunityCategory,
    opportunity_candidate_evidence,
)
from app.qualification.config import IcpConfigModel
from app.qualification.models import IcpConfig, QualificationResult
from app.research.models import ResearchRun
from app.scoring.config import ScoringConfigModel
from app.scoring.dimensions import Dimension
from app.scoring.engine import Assessment, assess
from app.scoring.models import ScoreSnapshot, ScoringConfig
from app.similarity.engine import ReferenceProfile, SimilarityResult, compare
from app.similarity.engine import best as best_similarity


class MissingConfiguration(Exception):
    pass


@dataclass
class Context:
    run: ResearchRun
    facts: Facts
    candidates: list[Candidate]
    solved_by: dict[str, list[str]]
    services: list[ServiceInfo]
    references: list[ReferenceProfile]
    icp_config_id: uuid.UUID
    icp_config: IcpConfigModel
    scoring_config_id: uuid.UUID
    scoring_config: ScoringConfigModel
    suppressed_by: str | None


async def load_facts(db: AsyncSession, run: ResearchRun) -> Facts:
    rows = (
        await db.execute(
            select(Observation)
            .where(Observation.research_run_id == run.id, Observation.attempt == run.retry_count)
            .options(selectinload(Observation.evidence))
            .order_by(Observation.created_at, Observation.id)
        )
    ).scalars()
    return Facts(
        Fact(
            r.key,
            r.value,
            float(r.confidence),
            str(r.evidence_id),
            r.evidence.source_url,
            r.evidence.evidence_text,
        )
        for r in rows
    )


async def catalogue(db: AsyncSession) -> list[ServiceInfo]:
    """The confirmed, active services in catalogue order (only these are ever recommended)."""
    services = (
        await db.execute(
            select(Service)
            .where(Service.confirmed.is_(True), Service.is_active.is_(True))
            .order_by(Service.created_at, Service.key)
        )
    ).scalars()
    return [ServiceInfo(s.key, s.name, tuple(s.solves)) for s in services]


def solved_by_map(services: list[ServiceInfo]) -> dict[str, list[str]]:
    mapping: dict[str, list[str]] = {}
    for service in services:
        for category in service.solves:
            mapping.setdefault(category, []).append(service.key)
    return mapping


async def references(db: AsyncSession) -> list[ReferenceProfile]:
    rows = (
        await db.execute(select(ReferenceProject).options(selectinload(ReferenceProject.services)))
    ).scalars()
    return [
        ReferenceProfile(
            r.name, r.industry, r.problem, tuple(s.key for s in r.services), r.profile_complete
        )
        for r in rows
    ]


async def _suppressed(db: AsyncSession, domain: str) -> str | None:
    hit = (
        await db.execute(
            select(Suppression).where(
                Suppression.kind == SuppressionKind.DOMAIN, Suppression.value == domain
            )
        )
    ).scalar_one_or_none()
    if hit:
        return f"domain {domain}: {hit.reason}"
    account = (
        await db.execute(
            select(Suppression)
            .join(AccountDomain, cast(AccountDomain.account_id, String) == Suppression.value)
            .where(Suppression.kind == SuppressionKind.ACCOUNT, AccountDomain.domain == domain)
        )
    ).scalar_one_or_none()
    return f"account for {domain}: {account.reason}" if account else None


async def load_context(db: AsyncSession, run_id: uuid.UUID) -> Context:
    run = await db.get(ResearchRun, run_id)
    assert run is not None
    facts = await load_facts(db, run)
    icp_row = (
        await db.execute(select(IcpConfig).where(IcpConfig.is_active.is_(True)))
    ).scalar_one_or_none()
    scoring_row = (
        await db.execute(select(ScoringConfig).where(ScoringConfig.is_active.is_(True)))
    ).scalar_one_or_none()
    if icp_row is None or scoring_row is None:
        # Every result records the configuration version it used; never guess one.
        raise MissingConfiguration(
            "No active ICP or scoring configuration. An admin must activate one."
        )
    services = await catalogue(db)
    return Context(
        run=run,
        facts=facts,
        candidates=detect(facts),
        solved_by=solved_by_map(services),
        services=services,
        references=await references(db),
        icp_config_id=icp_row.id,
        icp_config=IcpConfigModel.model_validate(icp_row.config),
        scoring_config_id=scoring_row.id,
        scoring_config=ScoringConfigModel.model_validate(scoring_row.config),
        suppressed_by=await _suppressed(db, run.normalised_domain),
    )


def matches_and_similarity(ctx: Context) -> tuple[list[Match], list[SimilarityResult]]:
    matches = match_services(ctx.candidates, ctx.services)
    industries = [f.value["name"] for f in ctx.facts.all("company.industry")]
    problems = [c.problem for c in ctx.candidates]
    results = [
        compare(r, industries=industries, problems=problems, matches=matches)
        for r in ctx.references
    ]
    return matches, results


def run_assessment(ctx: Context) -> Assessment:
    _, results = matches_and_similarity(ctx)
    top = best_similarity(results)
    similarity = Dimension(top.score, note=top.because) if top else None
    return assess(
        ctx.facts,
        ctx.candidates,
        solved_by=ctx.solved_by,
        icp_config=ctx.icp_config,
        scoring_config=ctx.scoring_config,
        suppressed_by=ctx.suppressed_by,
        possible_duplicates=list(ctx.run.possible_duplicate_of),
        client_similarity=similarity,
    )


def _evidence_uuids(ids: list[str]) -> list[uuid.UUID]:
    return [uuid.UUID(i) for i in dict.fromkeys(ids)]


async def detect_stage(
    run_id: uuid.UUID, sessionmaker: async_sessionmaker[AsyncSession]
) -> dict[str, Any]:
    async with sessionmaker() as db:
        ctx = await load_context(db, run_id)
        await db.execute(
            delete(OpportunityCandidate).where(OpportunityCandidate.research_run_id == run_id)
        )
        categories = {
            c.key: c.id for c in (await db.execute(select(OpportunityCategory))).scalars()
        }
        for candidate in ctx.candidates:
            row = OpportunityCandidate(
                research_run_id=run_id,
                category_id=categories[candidate.category],
                title=candidate.title,
                problem_statement=candidate.problem,
                confidence=Decimal(str(candidate.confidence)),
                rule_key=candidate.rule_key,
            )
            db.add(row)
            await db.flush()
            for evidence_id in _evidence_uuids(candidate.evidence_ids):
                await db.execute(
                    opportunity_candidate_evidence.insert().values(
                        candidate_id=row.id, evidence_id=evidence_id
                    )
                )
        await db.commit()
    return {
        "candidates": len(ctx.candidates),
        "categories": [c.category for c in ctx.candidates],
        "best": ctx.candidates[0].title if ctx.candidates else None,
    }


async def qualify_stage(
    run_id: uuid.UUID, sessionmaker: async_sessionmaker[AsyncSession]
) -> dict[str, Any]:
    async with sessionmaker() as db:
        ctx = await load_context(db, run_id)
        result = run_assessment(ctx).icp
        await db.execute(
            delete(QualificationResult).where(QualificationResult.research_run_id == run_id)
        )
        payload = result.as_json()
        db.add(
            QualificationResult(
                research_run_id=run_id,
                icp_config_id=ctx.icp_config_id,
                icp_fit=None if result.icp_fit is None else Decimal(str(result.icp_fit)),
                components=payload["components"],
                negative_icp_hits=payload["negative_icp_hits"],
                hard_reject=result.hard_reject,
                rejection_reason=result.rejection_reason,
                explanation=result.explanation,
            )
        )
        await db.commit()
    return {
        "icp_fit": result.icp_fit,
        "hard_reject": result.hard_reject,
        "rejection_reason": result.rejection_reason.value if result.rejection_reason else None,
        "industry_tier": result.industry_tier,
        "is_agency": result.is_agency,
    }


def _decimal(value: float | None) -> Decimal | None:
    return None if value is None else Decimal(str(round(value, 2)))


async def score_stage(
    run_id: uuid.UUID, sessionmaker: async_sessionmaker[AsyncSession]
) -> dict[str, Any]:
    async with sessionmaker() as db:
        ctx = await load_context(db, run_id)
        assessment = run_assessment(ctx)
        scores = assessment.scores
        db.add(
            ScoreSnapshot(
                research_run_id=run_id,
                scoring_config_id=ctx.scoring_config_id,
                **{name: _decimal(scores[name]) for name in scores},
                priority_score=_decimal(assessment.priority_score),
                priority_band=assessment.priority_band,
                qualifies=assessment.qualifies,
                breakdown={
                    **assessment.breakdown,
                    "attempt": ctx.run.retry_count,
                    "service_key": assessment.service_key,
                },
            )
        )
        await db.commit()
    return {
        "priority_score": assessment.priority_score,
        "priority_band": assessment.priority_band.value if assessment.priority_band else None,
        "qualifies": assessment.qualifies,
        "not_qualified_because": assessment.not_qualified_because,
    }
