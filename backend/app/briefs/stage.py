"""Match and brief stages: store service matches, similarity results, every brief claim (with
its evidence and support links) and the lead brief itself."""

import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.briefs.claims import SECTIONS
from app.briefs.models import LeadBrief
from app.briefs.template import BriefInputs, company_name
from app.briefs.writer import write_brief
from app.catalogue.models import ReferenceProject, Service, ServiceMatch
from app.core.enums import BriefMode
from app.evidence.models import Claim, claim_evidence, claim_support
from app.providers.ai import AIProvider
from app.scoring import stage as scoring
from app.similarity.engine import best as best_similarity
from app.similarity.models import SimilarityResult as SimilarityRow


async def match_stage(
    run_id: uuid.UUID, sessionmaker: async_sessionmaker[AsyncSession]
) -> dict[str, Any]:
    async with sessionmaker() as db:
        ctx = await scoring.load_context(db, run_id)
        matches, results = scoring.matches_and_similarity(ctx)
        await db.execute(delete(ServiceMatch).where(ServiceMatch.research_run_id == run_id))
        await db.execute(delete(SimilarityRow).where(SimilarityRow.research_run_id == run_id))
        service_ids = {s.key: s.id for s in (await db.execute(select(Service))).scalars()}
        for match in matches:
            db.add(
                ServiceMatch(
                    research_run_id=run_id,
                    slot=match.slot,
                    service_id=service_ids[match.service.key],
                    rationale=match.rationale,
                    confidence=Decimal(str(match.confidence)),
                )
            )
        project_ids = {p.name: p.id for p in (await db.execute(select(ReferenceProject))).scalars()}
        for result in results:
            db.add(
                SimilarityRow(
                    research_run_id=run_id,
                    reference_project_id=project_ids[result.project],
                    similarity_score=None if result.score is None else Decimal(str(result.score)),
                    similar_because=result.because,
                )
            )
        await db.commit()
    top = best_similarity(results)
    return {
        "services": [{"slot": m.slot.value, "service": m.service.key} for m in matches],
        "similarity": {"project": top.project, "score": top.score} if top else None,
        "reference_profiles_complete": sum(1 for r in ctx.references if r.profile_complete),
    }


async def brief_stage(
    run_id: uuid.UUID, sessionmaker: async_sessionmaker[AsyncSession], ai: AIProvider
) -> dict[str, Any]:
    async with sessionmaker() as db:
        ctx = await scoring.load_context(db, run_id)
        matches, results = scoring.matches_and_similarity(ctx)
        assessment = scoring.run_assessment(ctx)
        inputs = BriefInputs(
            facts=ctx.facts,
            candidates=ctx.candidates,
            matches=matches,
            similarity=best_similarity(results),
            assessment=assessment,
            reference_names=[r.name for r in ctx.references],
        )
        draft, generated_by = await write_brief(inputs, ai)

        claim_ids: dict[str, uuid.UUID] = {}
        rows: list[tuple[Claim, list[str], list[str]]] = []
        for claim in draft.claims():
            row = Claim(
                research_run_id=run_id,
                claim_class=claim.claim_class,
                subject=claim.subject[:120],
                statement=claim.text,
                confidence=Decimal(str(round(claim.confidence, 2))),
            )
            db.add(row)
            rows.append((row, claim.evidence_ids, claim.supports))
        await db.flush()
        for (row, _, _), claim in zip(rows, draft.claims(), strict=True):
            claim_ids[claim.ref] = row.id
        for row, evidence_ids, supports in rows:
            for evidence_id in dict.fromkeys(evidence_ids):
                await db.execute(
                    claim_evidence.insert().values(
                        claim_id=row.id, evidence_id=uuid.UUID(evidence_id)
                    )
                )
            for ref in dict.fromkeys(supports):
                await db.execute(
                    claim_support.insert().values(
                        claim_id=row.id, supported_by_claim_id=claim_ids[ref]
                    )
                )

        sections: dict[str, Any] = {
            "summary": {
                "company": company_name(ctx.facts),
                "domain": ctx.run.normalised_domain,
                "priority_score": assessment.priority_score,
                "priority_band": assessment.priority_band.value
                if assessment.priority_band
                else None,
                "qualifies": assessment.qualifies,
                **{
                    k: assessment.scores[k]
                    for k in (
                        "icp_score",
                        "opportunity_score",
                        "intent_score",
                        "buyer_confidence",
                        "data_confidence",
                    )
                },
            }
        }
        for name in SECTIONS:
            section = draft.sections[name]
            sections[name] = {
                "source": section.source,
                "claims": [
                    {
                        "claim_id": str(claim_ids[c.ref]),
                        "class": c.claim_class.value,
                        "text": c.text,
                        "evidence_ids": c.evidence_ids,
                    }
                    for c in section.claims
                ],
                "unknown": section.unknown,
                "notes": section.notes,
            }
        await db.execute(delete(LeadBrief).where(LeadBrief.research_run_id == run_id))
        db.add(
            LeadBrief(
                research_run_id=run_id,
                sections=sections,
                mode=BriefMode.AI if generated_by["mode"] == "ai" else BriefMode.TEMPLATE,
                generated_by={**generated_by, "attempt": ctx.run.retry_count},
            )
        )
        await db.commit()  # the deferred trigger checks every fact/inference has evidence here
    return {
        "mode": generated_by["mode"],
        "claims": len(draft.claims()),
        "dropped": len(generated_by["dropped"]),
        "ai_sections": generated_by["ai_sections"],
        "ai_error": generated_by.get("ai_error"),
    }
