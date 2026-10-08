"""Writes the lead brief: template first, then (optionally) AI sections that replace template
sections only when at least one AI claim survives grounding. Every claim, from either source,
passes the same validator."""

from typing import Any

from app.briefs import ai_writer, template
from app.briefs.claims import Draft, DraftClaim
from app.briefs.grounding import validate
from app.core.enums import ClaimClass
from app.providers.ai import AIProvider, NullAIProvider
from app.providers.errors import ProviderError


async def write_brief(inputs: template.BriefInputs, ai: AIProvider) -> tuple[Draft, dict[str, Any]]:
    draft = template.build(inputs)
    evidence = template.evidence_index(inputs.facts)
    vocab = template.vocabulary(inputs)

    kept, dropped = validate(draft.claims(), evidence, vocab)
    survivors = {id(c) for c in kept}
    for section in draft.sections.values():
        section.claims = [c for c in section.claims if id(c) in survivors]
    generated_by: dict[str, Any] = {
        "mode": "template",
        "provider": ai.name,
        "model": ai.model,
        "prompt_version": ai_writer.PROMPT_VERSION,
        "dropped": [dict(d, source="template") for d in dropped],
        "ai_sections": [],
    }
    if isinstance(ai, NullAIProvider):
        return draft, generated_by

    problems = [
        c
        for c in draft.sections["problem_detected"].claims
        if c.claim_class == ClaimClass.INFERENCE
    ]
    try:
        proposed = await ai_writer.generate(ai, inputs, problems)
    except ProviderError as exc:
        generated_by["ai_error"] = exc.message
        return draft, generated_by

    for name, claims in proposed.items():
        if not claims:
            continue
        # Validate together with the problem claims so recommendations can rest on them.
        checked, rejected = validate([*_copies(problems), *claims], evidence, vocab)
        ai_kept = [c for c in checked if c.ref.startswith("ai.")]
        generated_by["dropped"] += [dict(d, source="ai") for d in rejected]
        if ai_kept:
            section = draft.sections[name]
            section.claims, section.unknown, section.source = ai_kept, None, "ai"
            generated_by["ai_sections"].append(name)
    if generated_by["ai_sections"]:
        generated_by["mode"] = "ai"
    return draft, generated_by


def _copies(claims: list[DraftClaim]) -> list[DraftClaim]:
    return [
        DraftClaim(
            c.claim_class,
            c.text,
            list(c.evidence_ids),
            list(c.supports),
            c.subject,
            c.confidence,
            c.ref,
        )
        for c in claims
    ]
