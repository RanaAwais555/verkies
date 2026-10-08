"""The scoring dimensions (SCORING_SPEC.md §2). Each is a pure function returning a Dimension:
a 0-100 score or None (Unknown), the evidence it used and a one-line note. Unknown is never 0.
ICP Fit comes from the ICP engine; Client Similarity arrives with reference profiles (1.5).
"""

import re
from dataclasses import dataclass, field
from datetime import UTC, date, datetime

from app.intelligence.facts import Facts
from app.intelligence.people import named_people
from app.opportunities.detectors import Candidate
from app.signals.classify import MEDIUM, STRENGTH, STRONG, VERY_STRONG

DECISION_ROLE = re.compile(
    r"\b(founder|co-?founder|ceo|cto|coo|cfo|cmo|cpo|chief|managing|director|head of|partner|"
    r"owner|president|principal)\b",
    re.I,
)
STRONG_SIGNAL_KEYS = ("hiring.tech_roles", "product.waitlist")


@dataclass
class Dimension:
    score: float | None
    evidence_ids: list[str] = field(default_factory=list)
    note: str = ""

    @property
    def known(self) -> bool:
        return self.score is not None


def _clamp(value: float) -> float:
    return round(max(0.0, min(100.0, value)), 2)


def evidence_strength(facts: Facts) -> Dimension:
    """Quantity, spread and quality of the evidence behind this prospect."""
    present = [f for f in facts if f.value not in (False, None, [])]
    if not present:
        return Dimension(0.0, note="No positive evidence was found")
    pages = {f.source_url for f in present}
    mean_conf = sum(f.confidence for f in present) / len(present)
    score = 2.5 * min(len(present), 20) + 6 * min(len(pages), 5) + 20 * mean_conf
    return Dimension(
        _clamp(score),
        note=f"{len(present)} findings from {len(pages)} pages, mean confidence {mean_conf:.2f}",
    )


def buyer_confidence(facts: Facts) -> Dimension:
    people = named_people(facts)
    deciders = [f for f in people if DECISION_ROLE.search(str(f.value.get("title", "")))]
    contact_keys = [
        k for k in ("conversion.email_addresses", "conversion.phone_numbers") if facts.present(k)
    ]
    if deciders:
        score, note = (
            75 + 5 * min(len(deciders) - 1, 3),
            (f"Named decision maker(s): {', '.join(f.value['name'] for f in deciders[:3])}"),
        )
    elif people:
        score, note = 50, f"Named people, none with a decision-making title ({len(people)})"
    else:
        score, note = 15, "No named people found on the site or in the register"
    if contact_keys:
        score += 10
        note += "; published contact route"
    ids = [f.evidence_id for f in (deciders or people)] + facts.evidence(*contact_keys)
    return Dimension(_clamp(score), ids, note)


KEY_FIELDS = (
    ("company.name", ("company.name",)),
    ("description", ("company.description",)),
    ("industry", ("company.industry",)),
    ("location", ("company.address", "company.country_hint")),
    (
        "contact route",
        ("conversion.email_addresses", "conversion.phone_numbers", "conversion.contact_form"),
    ),
    ("people", ("company.person",)),
    ("company profile", ("company.linkedin_company_url",)),
)


def data_confidence(facts: Facts) -> Dimension:
    """How much of the account record is backed by evidence, weighted by its confidence."""
    total = 0.0
    found: list[str] = []
    ids: list[str] = []
    for label, keys in KEY_FIELDS:
        best = max(
            (f.confidence for k in keys for f in facts.all(k) if f.value not in (False, None, [])),
            default=0.0,
        )
        if best:
            total += best
            found.append(label)
            ids += facts.evidence(*keys)
    score = 100 * total / len(KEY_FIELDS)
    missing = [label for label, _ in KEY_FIELDS if label not in found]
    note = f"Evidenced: {', '.join(found) or 'nothing'}" + (
        f"; Unknown: {', '.join(missing)}" if missing else ""
    )
    return Dimension(_clamp(score), ids, note)


SIGNAL_KEYS = ("signal.job_posting", "signal.news")
SIGNAL_LABELS = {
    "developer_hiring": "hiring developers",
    "cto_hiring": "hiring a technology leader",
    "product_hiring": "hiring product roles",
    "funding": "announced funding",
    "product_launch": "launched a product",
    "new_leader": "new leadership",
    "acquisition": "an acquisition",
    "expansion": "expanding",
    "new_service": "a new service",
    "hiring": "hiring",
}


def _signals(facts: Facts) -> dict[str, list[str]]:
    """Signal type -> evidence ids, from the signals stage (job boards and company feeds)."""
    found: dict[str, list[str]] = {}
    for key in SIGNAL_KEYS:
        for fact in facts.all(key):
            found.setdefault(str(fact.value.get("signal")), []).append(fact.evidence_id)
    return found


def intent(facts: Facts) -> Dimension:
    """Evidence the company is changing or building now (master context §9 signal strengths).
    The strongest evidenced signal sets the score; Unknown when nothing says so."""
    options: list[tuple[float, list[str], str]] = []
    if facts.present("hiring.tech_roles"):
        score = 80 + (10 if facts.has("hiring.job_board") else 0)
        options.append(
            (
                score,
                facts.evidence("hiring.tech_roles", "hiring.job_board"),
                "Hiring engineering or product roles now",
            )
        )
    signals = _signals(facts)
    by_strength: dict[str, list[str]] = {}
    for kind in signals:
        by_strength.setdefault(STRENGTH.get(kind, MEDIUM), []).append(kind)
    for strength, base, step, cap in (
        (VERY_STRONG, 85, 5, 100),
        (STRONG, 70, 5, 80),
        (MEDIUM, 50, 5, 60),
    ):
        kinds = sorted(by_strength.get(strength, []))
        if kinds:
            ids = [i for k in kinds for i in signals[k]]
            label = ", ".join(SIGNAL_LABELS.get(k, k) for k in kinds)
            options.append((min(cap, base + step * (len(kinds) - 1)), ids, f"Signals: {label}"))
    if facts.present("product.waitlist"):
        options.append((60, facts.evidence("product.waitlist"), "Pre-launch waitlist"))
    if facts.has("hiring.careers_page"):
        options.append(
            (40, facts.evidence("hiring.careers_page"), "Careers page, no technical roles listed")
        )
    if not options:
        return Dimension(None, note="No intent signal found (Unknown, not zero)")
    best = max(options, key=lambda o: o[0])
    ids = list(dict.fromkeys(i for o in options if o[0] >= best[0] - 10 for i in o[1]))
    return Dimension(float(best[0]), ids, best[2])


def _recency_score(days: int) -> float | None:
    for limit, score in ((30, 90.0), (90, 75.0), (180, 55.0), (365, 35.0)):
        if days <= limit:
            return score
    return None


def timing(facts: Facts, today: date | None = None) -> Dimension:
    """How current the evidence of change is: the most recent dated signal decides. Roles open
    at the time of research count as now."""
    today = today or datetime.now(UTC).date()
    options: list[tuple[float, list[str], str]] = []
    dated: list[tuple[date, str]] = []
    undated_open: list[str] = []
    for key in SIGNAL_KEYS:
        for fact in facts.all(key):
            published = fact.value.get("published")
            if published:
                try:
                    dated.append((date.fromisoformat(published), fact.evidence_id))
                except ValueError:
                    continue
            elif key == "signal.job_posting":
                undated_open.append(fact.evidence_id)
    if dated:
        latest = max(d for d, _ in dated)
        score = _recency_score((today - latest).days)
        if score is not None:
            ids = [i for d, i in dated if d == latest]
            options.append((score, ids, f"Latest signal dated {latest.isoformat()}"))
    if undated_open:
        options.append((75.0, undated_open, "Job postings open at the time of research"))
    if facts.present("hiring.tech_roles"):
        options.append(
            (75.0, facts.evidence("hiring.tech_roles"), "Roles open at the time of research")
        )
    if facts.present("product.waitlist") or facts.value("website.holding_page") == "coming_soon":
        options.append(
            (65.0, facts.evidence("product.waitlist", "website.holding_page"), "About to launch")
        )
    if not options:
        return Dimension(None, note="No time-bound signal found")
    best = max(options, key=lambda o: o[0])
    return Dimension(best[0], best[1], best[2])


def opportunity(candidates: list[Candidate], min_confidence: float) -> Dimension:
    strong = [c for c in candidates if c.confidence >= min_confidence]
    if not candidates:
        return Dimension(0.0, note="No commercial opportunity detected")
    best = candidates[0]
    score = best.confidence * 100 + 5 * max(len(strong) - 1, 0)
    ids = [i for c in candidates[:3] for i in c.evidence_ids]
    return Dimension(
        _clamp(score),
        list(dict.fromkeys(ids)),
        f"Best: {best.title} ({best.confidence:.2f}); {len(strong)} strong candidate(s)",
    )


def service_fit(
    candidates: list[Candidate], solved_by: dict[str, list[str]]
) -> tuple[Dimension, str | None]:
    """Best candidate that a confirmed Verkies service answers. Returns the service key too."""
    for candidate in candidates:
        services = solved_by.get(candidate.category, [])
        if services:
            return (
                Dimension(
                    _clamp(candidate.confidence * 100),
                    candidate.evidence_ids,
                    f"{candidate.title} -> {services[0]}",
                ),
                services[0],
            )
    return Dimension(
        0.0, note="No confirmed Verkies service answers the detected opportunities"
    ), None


def commercial_potential(facts: Facts, industry_tier: str | None) -> Dimension:
    base = {"S": 70, "A": 60, "B": 40}.get(industry_tier or "")
    extras: list[tuple[str, float, str]] = [
        ("product.subscription_pricing", 10, "recurring revenue"),
        ("product.payments", 5, "takes payments online"),
        ("product.login", 10, "runs a customer-facing application"),
        ("product.portal", 5, "has a portal"),
        ("hiring.tech_roles", 10, "is investing in technology"),
        ("conversion.trust_signals", 5, "regulated or accredited"),
    ]
    found = [(k, pts, why) for k, pts, why in extras if facts.present(k)]
    people = len(facts.all("company.person"))
    if base is None and not found:
        return Dimension(None, note="Industry Unknown and no budget indicators")
    score = (base if base is not None else 40) + sum(p for _, p, _ in found)
    if people >= 3:
        score += 5
    reasons = [why for _, _, why in found] + ([f"{people} named staff"] if people >= 3 else [])
    note = (f"Industry tier {industry_tier}" if industry_tier else "Industry Unknown") + (
        f"; {', '.join(reasons)}" if reasons else ""
    )
    return Dimension(_clamp(score), facts.evidence(*(k for k, _, _ in found)), note)


def problem_signal_count(candidates: list[Candidate]) -> int:
    return len({s for c in candidates for s in c.signals})


def has_strong_signal(facts: Facts) -> bool:
    return any(facts.present(k) for k in STRONG_SIGNAL_KEYS)
