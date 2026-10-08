"""The grounding validator (AI_SPEC.md §3): the gate every written claim passes.

A claim survives only if:
1. Facts and inferences cite at least one evidence ID that exists in this run.
2. Recommendations rest on at least one surviving fact or inference.
3. Every number, email, URL and proper name in the text appears in the cited evidence
   excerpts or in the known vocabulary (company name, Verkies service and reference project
   names, the person's name from evidence). A model cannot slip in a funding round, a
   headcount, a client or a person that the evidence does not show.
4. It is not generic filler ("help your business grow").

Everything dropped is returned with the reason, so it can be logged and audited.
"""

import re
from dataclasses import dataclass

from app.briefs.claims import DraftClaim
from app.core.enums import ClaimClass

BANNED = re.compile(
    r"\b(help (?:your|their) business grow|take (?:your|their) business to the next level|"
    r"cutting[- ]edge|world[- ]class|best[- ]in[- ]class|synerg\w*|game[- ]changer|"
    r"revolutioni[sz]e|unlock (?:your|their) (?:full )?potential|seamless(?:ly)? integrat\w*|"
    r"in today'?s (?:fast[- ]paced|digital) world|leverage (?:our|the) expertise)\b",
    re.I,
)
NUMBER = re.compile(
    r"(?<![\w.])(?:£|\$|€)?\d[\d,]*(?:\.\d+)?(?:%|k|m|bn|mn|million|billion|thousand)?(?![\w])",
    re.I,
)
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
URL = re.compile(r"https?://[^\s)\"']+|(?:www\.)[^\s)\"']+")
PROPER = re.compile(r"\b[A-Z][a-zA-Z0-9&'’.-]*(?:\s+[A-Z][a-zA-Z0-9&'’.-]*)*")
COMMON_CAPITALISED = frozenset(
    [
        "I",
        "A",
        "An",
        "The",
        "This",
        "That",
        "These",
        "Those",
        "It",
        "Its",
        "They",
        "Their",
        "There",
        "Here",
        "We",
        "Our",
        "You",
        "Your",
        "He",
        "She",
        "His",
        "Her",
        "Why",
        "How",
        "What",
        "When",
        "Where",
        "Who",
        "Which",
        "Now",
        "New",
        "No",
        "Not",
        "Yes",
        "And",
        "But",
        "Or",
        "If",
        "So",
        "As",
        "At",
        "By",
        "For",
        "From",
        "In",
        "On",
        "To",
        "With",
        "Without",
        "Of",
        "Also",
        "Then",
        "Than",
        "Unknown",
        "Fact",
        "Inference",
        "Recommendation",
        "Primary",
        "Secondary",
        "Expansion",
        "Next",
        "Open",
        "Offer",
        "Ask",
        "Start",
        "Send",
        "Book",
        "Share",
        "Lead",
        "Use",
        "Show",
        "Research",
        "Mention",
        "Suggest",
        "Propose",
        "Follow",
        "Reach",
        "Contact",
        "Call",
        "Email",
        "Note",
        "Consider",
        "Explain",
        "Review",
        "Focus",
        "Keep",
        "Find",
        "Check",
        "Website",
        "Site",
        "Homepage",
        "Page",
        "Pages",
        "Enquiries",
        "Enquiry",
        "Visitors",
        "Customers",
        "Clients",
        "Business",
        "CRM",
        "SEO",
        "MVP",
        "API",
        "UK",
        "US",
        "EU",
        "HTTPS",
        "HSTS",
        "AI",
        "JavaScript",
        "LinkedIn",
        "Google",
        "WordPress",
    ]
)


@dataclass(frozen=True)
class Evidence:
    id: str
    excerpt: str
    source_url: str


def _norm(text: str) -> str:
    return " ".join(text.lower().replace("’", "'").split())


def _number_variants(token: str) -> set[str]:
    bare = token.lstrip("£$€").rstrip("%")
    return {token.lower(), bare.lower(), bare.replace(",", "").lower()}  # "£2m" must appear as-is


def ungrounded_terms(text: str, sources: str, vocabulary: set[str]) -> list[str]:
    """Numbers, emails, URLs and proper names in text that appear in neither the cited
    evidence nor the vocabulary."""
    haystack = _norm(sources + " " + " ".join(vocabulary))
    compact = haystack.replace(",", "")
    missing: list[str] = []
    for match in NUMBER.finditer(text):
        token = match.group(0)
        if not any(v in haystack or v in compact for v in _number_variants(token)):
            missing.append(token)
    for pattern in (EMAIL, URL):
        for match in pattern.finditer(text):
            if _norm(match.group(0).rstrip(".,")) not in haystack:
                missing.append(match.group(0))
    for sentence in re.split(r"(?<=[.!?;:])\s+|\n", text):
        for i, match in enumerate(PROPER.finditer(sentence.strip())):
            phrase = match.group(0).strip(" .'’")
            words = [w for w in phrase.split() if w not in COMMON_CAPITALISED]
            if not words:
                continue
            if i == 0 and match.start() == 0 and len(phrase.split()) == 1:
                continue  # the sentence's first word is capitalised anyway
            candidate = _norm(" ".join(words))
            if (
                candidate
                and candidate not in haystack
                and all(_norm(w) not in haystack for w in words)
            ):
                missing.append(phrase)
    return missing


def validate(
    claims: list[DraftClaim], evidence: dict[str, Evidence], vocabulary: set[str]
) -> tuple[list[DraftClaim], list[dict[str, str]]]:
    kept: list[DraftClaim] = []
    dropped: list[dict[str, str]] = []

    def drop(claim: DraftClaim, reason: str) -> None:
        dropped.append(
            {
                "ref": claim.ref,
                "class": claim.claim_class.value,
                "text": claim.text[:300],
                "reason": reason,
            }
        )

    surviving_refs: set[str] = set()
    for claim in [c for c in claims if c.claim_class != ClaimClass.RECOMMENDATION] + [
        c for c in claims if c.claim_class == ClaimClass.RECOMMENDATION
    ]:
        text = claim.text.strip()
        if not text:
            drop(claim, "empty")
            continue
        if BANNED.search(text):
            drop(claim, f"generic filler: {BANNED.search(text).group(0)}")  # type: ignore[union-attr]
            continue
        valid_ids = [i for i in dict.fromkeys(claim.evidence_ids) if i in evidence]
        invalid = [i for i in claim.evidence_ids if i not in evidence]
        if invalid:
            drop(claim, f"cites evidence that does not exist: {', '.join(invalid[:3])}")
            continue
        if claim.claim_class in (ClaimClass.FACT, ClaimClass.INFERENCE) and not valid_ids:
            drop(claim, "no evidence cited")
            continue
        if claim.claim_class == ClaimClass.RECOMMENDATION:
            claim.supports = [r for r in claim.supports if r in surviving_refs]
            if not claim.supports:
                drop(claim, "rests on no surviving fact or inference")
                continue
        sources = " ".join(evidence[i].excerpt for i in valid_ids)
        if claim.claim_class == ClaimClass.RECOMMENDATION:
            supported = [c for c in kept if c.ref in claim.supports]
            sources += " " + " ".join(c.text for c in supported)
            sources += " " + " ".join(
                evidence[i].excerpt for c in supported for i in c.evidence_ids if i in evidence
            )
        missing = ungrounded_terms(text, sources, vocabulary)
        if missing:
            drop(claim, f"mentions what the evidence does not show: {', '.join(missing[:5])}")
            continue
        claim.evidence_ids = valid_ids
        kept.append(claim)
        surviving_refs.add(claim.ref)
    order = {id(c): i for i, c in enumerate(claims)}
    kept.sort(key=lambda c: order[id(c)])
    return kept, dropped
