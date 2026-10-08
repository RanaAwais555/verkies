"""ICP and negative-ICP evaluation (ICP_SPEC.md §2 and §5).

ICP Fit combines four evidenced components; an Unknown component is excluded and the rest
are renormalised. Negative rules are hard (reject), soft (points off) or review (flag for the
person approving). Hard rules need explicit evidence; an ambiguous case becomes a soft or
review hit, never a silent rejection.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from app.core.enums import RejectionReason
from app.intelligence.facts import Facts
from app.opportunities.detectors import Candidate
from app.qualification.config import IcpConfigModel
from app.scoring.dimensions import Dimension

COUNTRY_NAMES = {
    "united kingdom": "GB",
    "uk": "GB",
    "england": "GB",
    "scotland": "GB",
    "wales": "GB",
    "great britain": "GB",
    "united states": "US",
    "usa": "US",
    "canada": "CA",
    "australia": "AU",
    "ireland": "IE",
    "netherlands": "NL",
    "germany": "DE",
    "france": "FR",
    "switzerland": "CH",
    "sweden": "SE",
    "denmark": "DK",
    "united arab emirates": "AE",
    "uae": "AE",
}
FREELANCE_WORDS = ("freelance", "hire me", "available for", "open to work")


@dataclass
class Component:
    name: str
    score: float | None
    weight: float
    evidence_ids: list[str] = field(default_factory=list)
    note: str = ""


@dataclass
class NegativeHit:
    rule_id: str
    severity: str  # hard, soft, review
    reason: RejectionReason | None
    evidence_ids: list[str] = field(default_factory=list)
    note: str = ""


@dataclass
class IcpResult:
    icp_fit: float | None
    components: list[Component]
    hits: list[NegativeHit]
    hard_reject: bool
    rejection_reason: RejectionReason | None
    industry_tier: str | None
    explanation: str
    is_agency: bool = False

    def as_json(self) -> dict[str, Any]:
        return {
            "components": [vars(c) for c in self.components],
            "negative_icp_hits": [
                {**vars(h), "reason": h.reason.value if h.reason else None} for h in self.hits
            ],
        }


@dataclass
class IcpInputs:
    facts: Facts
    candidates: list[Candidate]
    evidence_strength: Dimension
    buyer_confidence: Dimension
    has_service_fit: bool
    suppressed_by: str | None = None
    possible_duplicates: list[str] = field(default_factory=list)


def evaluate(inputs: IcpInputs, config: IcpConfigModel) -> IcpResult:
    facts = inputs.facts
    tier, industry = _industry(facts, config, inputs.evidence_strength)
    components = [
        _need(inputs.candidates, config),
        industry,
        _activity(facts, config),
        _geography(facts, config),
    ]
    known = [c for c in components if c.score is not None]
    if known:
        weight = sum(c.weight for c in known)
        fit: float | None = sum(c.weight * (c.score or 0) for c in known) / weight
    else:
        fit = None

    hits = _negative_hits(inputs, config, tier)
    for hit in hits:
        if hit.severity == "soft" and fit is not None:
            fit -= config.negative_rules[hit.rule_id].penalty
    if fit is not None:
        fit = round(max(0.0, min(100.0, fit)), 2)

    hard = [h for h in hits if h.severity == "hard"]
    reason = hard[0].reason if hard else None
    return IcpResult(
        icp_fit=fit,
        components=components,
        hits=hits,
        hard_reject=bool(hard),
        rejection_reason=reason,
        industry_tier=tier,
        explanation=_explain(fit, components, hits),
        is_agency=any(h.rule_id == "agency" for h in hits),
    )


# --- components -------------------------------------------------------------------------


def _need(candidates: list[Candidate], config: IcpConfigModel) -> Component:
    weight = config.component_weights["need_evidence"]
    if not candidates:
        return Component("need_evidence", 0.0, weight, note="No evidenced need found")
    best = candidates[0]
    independent = len({s for c in candidates for s in c.signals})
    score = min(100.0, best.confidence * 100 + 3 * max(independent - 2, 0))
    return Component(
        "need_evidence",
        round(score, 2),
        weight,
        best.evidence_ids,
        f"{best.title} ({best.confidence:.2f}); {independent} independent need signals",
    )


def _industry(
    facts: Facts, config: IcpConfigModel, strength: Dimension
) -> tuple[str | None, Component]:
    weight = config.component_weights["industry"]
    found = facts.all("company.industry")
    if not found:
        return None, Component("industry", None, weight, note="Industry Unknown")
    best_tier: str | None = None
    best_fact = found[0]
    for fact in found:
        tier = config.tier_of(fact.value["name"])
        if tier is not None and (
            best_tier is None or config.tier_scores[tier] > config.tier_scores[best_tier]
        ):
            best_tier, best_fact = tier, fact
    name = best_fact.value["name"]
    score = config.tier_scores[best_tier] if best_tier else config.tier_scores["other"]
    note = f"{name}: tier {best_tier}" if best_tier else f"{name}: outside the ICP tiers"
    if best_tier == "B" and (strength.score or 0) < config.tier_b_evidence_threshold:
        score *= config.tier_b_multiplier
        threshold, multiplier = config.tier_b_evidence_threshold, config.tier_b_multiplier
        note += f" (tier B with evidence strength below {threshold:g}: x{multiplier})"
    return best_tier, Component("industry", round(score, 2), weight, [best_fact.evidence_id], note)


def _activity(facts: Facts, config: IcpConfigModel) -> Component:
    weight = config.component_weights["activity"]
    if facts.has("website.holding_page"):
        return Component(
            "activity",
            10.0,
            weight,
            facts.evidence("website.holding_page"),
            "Placeholder site only",
        )
    score = 40.0
    notes: list[str] = []
    keys: list[str] = []
    year = facts.value("website.copyright_year")
    current = datetime.now(UTC).year
    if isinstance(year, int) and year >= current - 1:
        score += 20
        notes.append("site updated recently")
        keys.append("website.copyright_year")
    stale = facts.value("website.stale_copyright")
    if isinstance(stale, int) and stale >= 3:
        score -= 20
        notes.append(f"copyright {stale} years old")
        keys.append("website.stale_copyright")
    for key, points, why in (
        ("hiring.careers_page", 15, "has a careers page"),
        ("hiring.tech_roles", 10, "is hiring"),
        ("company.social_profiles", 10, "keeps social profiles"),
        ("website.sitemap", 5, "publishes a sitemap"),
    ):
        if facts.present(key):
            score += points
            notes.append(why)
            keys.append(key)
    words = facts.value("seo.home_word_count")
    if isinstance(words, int) and words >= 150:
        score += 10
        notes.append("substantial homepage")
        keys.append("seo.home_word_count")
    return Component(
        "activity",
        round(max(0.0, min(100.0, score)), 2),
        weight,
        facts.evidence(*keys),
        "; ".join(notes) or "Few signs of activity",
    )


def _geography(facts: Facts, config: IcpConfigModel) -> Component:
    weight = config.component_weights["geography"]
    country: str | None = None
    fact = None
    city: str | None = None
    address = facts.first("company.address")
    if address is not None:
        raw = str(address.value.get("addressCountry", "")).strip()
        country = raw.upper() if len(raw) == 2 else COUNTRY_NAMES.get(raw.lower())
        city = address.value.get("addressLocality")
        fact = address if country else None
    if country is None:
        hints = sorted(facts.all("company.country_hint"), key=lambda f: -f.confidence)
        if hints:
            fact = hints[0]
            country = str(fact.value)
    if country is None or fact is None:
        return Component("geography", None, weight, note="Location Unknown")
    candidates = country.split("/")  # "US/CA" from a +1 phone number: take the lower score
    scores = []
    for code in candidates:
        region = next((r for r in config.regions if code in r.countries), None)
        bonus = config.focus_city_bonus if region and city and city in region.focus_cities else 0
        scores.append(
            (
                (region.score if region else config.other_country_score) + bonus,
                region.name if region else "outside priority regions",
            )
        )
    score, name = min(scores)
    return Component(
        "geography",
        round(min(100.0, score), 2),
        weight,
        [fact.evidence_id],
        f"{country} ({name})" + (f", {city}" if city else ""),
    )


# --- negative ICP -------------------------------------------------------------------------


def _negative_hits(
    inputs: IcpInputs, config: IcpConfigModel, tier: str | None
) -> list[NegativeHit]:
    facts = inputs.facts
    hits: list[NegativeHit] = []

    def add(
        rule: str,
        reason: RejectionReason | None,
        ids: list[str],
        note: str,
        severity: str | None = None,
    ) -> None:
        settings = config.negative_rules.get(rule)
        if settings is None or not settings.enabled:
            return
        hits.append(NegativeHit(rule, severity or settings.severity, reason, ids, note))

    if inputs.suppressed_by:
        add(
            "suppressed",
            RejectionReason.SUPPRESSED_ACCOUNT,
            [],
            f"On the suppression list ({inputs.suppressed_by})",
        )
    if facts.value("website.holding_page") == "parked":
        add(
            "parked_domain",
            RejectionReason.INACTIVE_COMPANY,
            facts.evidence("website.holding_page"),
            "Parked or for-sale domain",
        )
    if facts.has("company.closed_notice"):
        add(
            "closed",
            RejectionReason.INACTIVE_COMPANY,
            facts.evidence("company.closed_notice"),
            f"Closure notice: {', '.join(facts.value('company.closed_notice'))}",
        )
    personal = facts.value("company.personal_site_signals") or []
    if personal:
        freelance = any(any(w in p for w in FREELANCE_WORDS) for p in personal)
        reason = (
            RejectionReason.STUDENT_OR_FREELANCER
            if freelance
            else RejectionReason.HOBBY_OR_PERSONAL
        )
        # One phrase is not explicit enough to reject: flag it for the reviewer instead.
        add(
            "personal_site",
            reason,
            facts.evidence("company.personal_site_signals"),
            f"Personal or freelancer wording: {', '.join(personal)}",
            severity=None if len(personal) >= 2 else "review",
        )
    agency = facts.value("company.agency_signals") or []
    if agency:
        explicit = len(agency) >= 2 or any("agency" in a for a in agency)
        add(
            "agency",
            RejectionReason.COMPETITOR,
            facts.evidence("company.agency_signals"),
            f"Agency wording: {', '.join(agency)}. Route to the partnership pipeline, not sales.",
            severity=None if explicit else "review",
        )
    if inputs.possible_duplicates:
        add(
            "duplicate",
            RejectionReason.DUPLICATE,
            [],
            f"Domain already belongs to account(s) {', '.join(inputs.possible_duplicates)}",
        )

    strong = [c for c in inputs.candidates if c.confidence >= config.min_opportunity_confidence]
    if not strong:
        add(
            "no_commercial_opportunity",
            RejectionReason.NO_COMMERCIAL_OPPORTUNITY,
            [],
            "No opportunity above the confidence threshold",
        )
    if not inputs.has_service_fit:
        add(
            "no_relevant_service",
            RejectionReason.NO_RELEVANT_SERVICE,
            [],
            "No confirmed Verkies service answers the detected opportunities",
        )
    if (inputs.evidence_strength.score or 0) < config.insufficient_evidence_below:
        add(
            "insufficient_evidence",
            RejectionReason.INSUFFICIENT_EVIDENCE,
            [],
            f"Evidence strength {inputs.evidence_strength.score} is below "
            f"{config.insufficient_evidence_below:g}",
        )
    if (inputs.buyer_confidence.score or 0) < config.no_buyer_below:
        add(
            "no_reachable_buyer",
            RejectionReason.NO_REACHABLE_BUYER,
            inputs.buyer_confidence.evidence_ids,
            inputs.buyer_confidence.note,
        )
    if facts.has("company.industry") and tier is None:
        add(
            "irrelevant_industry",
            RejectionReason.IRRELEVANT_INDUSTRY,
            facts.evidence("company.industry"),
            "Industry outside every ICP tier",
        )
    techs = facts.technologies()
    modern = {"Next.js", "Nuxt", "React", "Vue.js", "Angular", "Svelte", "Gatsby"} & set(techs)
    if (
        facts.present("conversion.booking_tool")
        and facts.present("conversion.live_chat")
        and facts.present("conversion.home_ctas")
        and modern
        and not strong
    ):
        add(
            "existing_solution_sufficient",
            RejectionReason.EXISTING_SOLUTION_SUFFICIENT,
            facts.evidence("conversion.booking_tool", "conversion.live_chat"),
            "Modern stack with booking, chat and clear calls to action; no gap found",
        )
    return hits


def _explain(fit: float | None, components: list[Component], hits: list[NegativeHit]) -> str:
    parts = [
        f"{c.name.replace('_', ' ')}: {'Unknown' if c.score is None else f'{c.score:g}'} ({c.note})"
        for c in components
    ]
    text = f"ICP fit {'Unknown' if fit is None else f'{fit:g}'}. " + "; ".join(parts) + "."
    for severity, label in (
        ("hard", "Rejected"),
        ("review", "Needs review"),
        ("soft", "Penalties"),
    ):
        group = [h for h in hits if h.severity == severity]
        if group:
            text += f" {label}: " + "; ".join(h.note for h in group) + "."
    return text
