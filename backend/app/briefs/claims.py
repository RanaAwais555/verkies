"""Draft claims: what a brief section says, its class, and what it rests on (AI_SPEC.md §2)."""

from dataclasses import dataclass, field

from app.core.enums import ClaimClass

# The lead brief's sections, in display order (master context §11).
SECTIONS = (
    "company_overview",
    "problem_detected",
    "why_verkies",
    "why_now",
    "recommended_service",
    "best_buyer",
    "similar_project",
    "sales_angle",
    "risks",
    "next_action",
)


@dataclass
class DraftClaim:
    claim_class: ClaimClass
    text: str
    evidence_ids: list[str] = field(default_factory=list)
    # Other claims (by their `ref`) this one rests on; required for recommendations.
    supports: list[str] = field(default_factory=list)
    subject: str = ""
    confidence: float = 0.7
    ref: str = ""  # stable id within one brief, e.g. "problem_detected.0"


@dataclass
class Section:
    claims: list[DraftClaim] = field(default_factory=list)
    # Shown when there are no claims: what is Unknown, never a guess.
    unknown: str | None = None
    # Plain notes that are not claims (risks and limitations the system itself knows).
    notes: list[str] = field(default_factory=list)
    source: str = "template"  # template or ai


@dataclass
class Draft:
    sections: dict[str, Section]
    dropped: list[dict[str, str]] = field(default_factory=list)

    def claims(self) -> list[DraftClaim]:
        return [c for s in self.sections.values() for c in s.claims]
