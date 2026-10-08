"""Similarity to Verkies' previous work (master context §11).

Compares business problems, not just industries. A reference project is compared only when
its profile is complete (an admin has filled in the fields the public site does not state);
otherwise the result is Unknown and the brief says so. Nothing is inferred about a reference
project that its profile does not record.
"""

from dataclasses import dataclass

from app.catalogue.matching import Match

WEIGHTS = {"problem": 0.4, "services": 0.3, "industry": 0.3}
STOPWORDS = frozenset(
    "a an and the of for to in on with by from their its it is are was were be or as at that "  # noqa: SIM905
    "this they we our us your".split()
)


@dataclass(frozen=True)
class ReferenceProfile:
    name: str
    industry: str | None
    problem: str | None
    service_keys: tuple[str, ...]
    profile_complete: bool


@dataclass(frozen=True)
class SimilarityResult:
    project: str
    score: float | None
    because: str


def _words(text: str) -> set[str]:
    return {
        w
        for w in "".join(c.lower() if c.isalnum() else " " for c in text).split()
        if len(w) > 3 and w not in STOPWORDS
    }


def compare(
    profile: ReferenceProfile,
    *,
    industries: list[str],
    problems: list[str],
    matches: list[Match],
) -> SimilarityResult:
    if not profile.profile_complete:
        return SimilarityResult(profile.name, None, "Reference profile incomplete: Unknown")
    reasons: list[str] = []
    score = 0.0
    industry = (profile.industry or "").lower()
    if industry and any(i in industry or industry in i for i in industries):
        score += WEIGHTS["industry"] * 100
        reasons.append(f"same industry ({profile.industry})")
    services = {m.service.key for m in matches}
    shared = services & set(profile.service_keys)
    if shared and profile.service_keys:
        score += WEIGHTS["services"] * 100 * len(shared) / len(set(profile.service_keys) | services)
        reasons.append(f"same services ({', '.join(sorted(shared))})")
    if profile.problem:
        reference = _words(profile.problem)
        prospect = set().union(*(_words(p) for p in problems)) if problems else set()
        overlap = reference & prospect
        if reference and overlap:
            score += WEIGHTS["problem"] * 100 * min(1.0, len(overlap) / max(4, len(reference) / 3))
            reasons.append(f"similar problem ({', '.join(sorted(overlap)[:4])})")
    because = "Similar because " + "; ".join(reasons) if reasons else "No meaningful overlap"
    return SimilarityResult(profile.name, round(min(100.0, score), 2), because)


def best(results: list[SimilarityResult]) -> SimilarityResult | None:
    known = [r for r in results if r.score is not None and r.score > 0]
    return max(known, key=lambda r: r.score or 0) if known else None
