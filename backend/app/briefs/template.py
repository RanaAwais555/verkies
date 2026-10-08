"""Template-mode lead brief: deterministic wording built only from evidence and engine output.

This is the mode that always works (no AI needed). Its claims go through the same grounding
validator as AI-written ones, so a template bug cannot slip an ungrounded statement through.
"""

import json
from dataclasses import dataclass

from app.briefs.claims import Draft, DraftClaim, Section
from app.briefs.grounding import Evidence
from app.catalogue.matching import Match
from app.core.enums import ClaimClass, ServiceSlot
from app.intelligence.facts import Fact, Facts
from app.intelligence.people import named_people
from app.opportunities.detectors import Candidate
from app.scoring.dimensions import DECISION_ROLE
from app.scoring.engine import Assessment
from app.signals.jobs import PROVIDER_NAMES
from app.similarity.engine import SimilarityResult

SALES_ANGLES = {
    "crm": "Open with how {who} lose time between an enquiry arriving and a client being onboarded; "
    "offer a short review of their intake process and show a working intake-to-portal flow.",
    "website_rebuild": "Lead with what the current website is costing them in trust and enquiries; "
    "show a before-and-after of a rebuilt, maintainable site.",
    "conversion_optimization": "Lead with the visitors they already have but do not convert; offer a "
    "short audit of the path from visit to enquiry.",
    "booking_system": "Lead with the back-and-forth of arranging consultations; show online booking "
    "with reminders.",
    "seo": "Lead with the questions their customers search for and the pages they are missing; offer "
    "a content and search review.",
    "mvp_development": "Lead with speed to a first launch: a fixed-scope MVP in weeks, not months.",
    "saas_development": "Lead with capacity: an experienced product team that ships while they keep hiring.",
    "internal_tools": "Lead with capacity: an experienced team that builds while they keep hiring.",
    "application_modernization": "Lead with the cost and risk of the ageing application; propose a "
    "phased modernisation.",
    "mobile_application": "Lead with their existing subscribers and what a companion app adds.",
    "analytics": "Lead with visibility: knowing which pages and channels bring enquiries.",
}
SLOT_LABEL = {
    ServiceSlot.PRIMARY: "Primary",
    ServiceSlot.SECONDARY: "Secondary",
    ServiceSlot.EXPANSION: "Expansion",
}


@dataclass
class BriefInputs:
    facts: Facts
    candidates: list[Candidate]
    matches: list[Match]
    similarity: SimilarityResult | None
    assessment: Assessment
    reference_names: list[str]


def evidence_index(facts: Facts) -> dict[str, Evidence]:
    """Evidence a claim may cite: the excerpt plus the observation's structured value, both
    taken from the same page."""
    index: dict[str, Evidence] = {}
    for fact in facts:
        value = fact.value if isinstance(fact.value, str) else json.dumps(fact.value, default=str)
        index[fact.evidence_id] = Evidence(
            fact.evidence_id, f"{fact.excerpt} {value}", fact.source_url
        )
    return index


def vocabulary(inputs: BriefInputs) -> set[str]:
    words = {"Verkies"}
    words.update(str(f.value) for f in inputs.facts.all("company.name"))
    words.update(m.service.name for m in inputs.matches)
    words.update(inputs.reference_names)
    words.update(str(f.value.get("name", "")) for f in inputs.facts.all("company.person"))
    # The engines' own stated reasons may be quoted (they are VROS output, not web claims).
    words.update(inputs.assessment.not_qualified_because)
    words.add("ICP")
    return {w for w in words if w}


def lower_first(title: str) -> str:
    """'Website rebuild' -> 'website rebuild', but 'MVP build' and 'CRM' stay as written."""
    first = title.split()[0] if title else ""
    return title if first.isupper() and len(first) > 1 else title[:1].lower() + title[1:]


def company_name(facts: Facts) -> str | None:
    named = sorted(facts.all("company.name"), key=lambda f: -f.confidence)
    return str(named[0].value) if named else None


def decision_maker(facts: Facts):  # type: ignore[no-untyped-def]
    people = named_people(facts)
    deciders = [p for p in people if DECISION_ROLE.search(str(p.value.get("title", "")))]
    found = deciders or people
    return found[0] if found else None


def build(inputs: BriefInputs) -> Draft:
    facts = inputs.facts
    sections: dict[str, Section] = {}

    overview: list[DraftClaim] = []
    name_fact = facts.first("company.name")
    description = facts.first("company.description")
    if name_fact and description:
        overview.append(
            DraftClaim(
                ClaimClass.FACT,
                f"{name_fact.value}: {str(description.value)[:220]}",
                [name_fact.evidence_id, description.evidence_id],
                subject="company.overview",
                ref="overview.0",
            )
        )
    elif name_fact and name_fact.confidence >= 0.6:
        overview.append(
            DraftClaim(
                ClaimClass.FACT,
                f"{name_fact.value}.",
                [name_fact.evidence_id],
                subject="company.name",
                ref="overview.0",
            )
        )
    elif name_fact:
        overview.append(
            DraftClaim(
                ClaimClass.INFERENCE,
                f"Name taken from the page title only: {name_fact.value}.",
                [name_fact.evidence_id],
                subject="company.name",
                ref="overview.0",
                confidence=name_fact.confidence,
            )
        )
    industries = facts.all("company.industry")
    if industries:
        names = sorted({str(f.value["name"]) for f in industries})
        overview.append(
            DraftClaim(
                ClaimClass.INFERENCE,
                f"Industry: {', '.join(names)}.",
                [f.evidence_id for f in industries],
                subject="company.industry",
                ref="overview.1",
                confidence=max(f.confidence for f in industries),
            )
        )
    address = facts.first("company.address")
    if address:
        place = ", ".join(
            v for k, v in address.value.items() if k in ("addressLocality", "addressCountry")
        )
        overview.append(
            DraftClaim(
                ClaimClass.FACT,
                f"Located in {place}.",
                [address.evidence_id],
                subject="company.location",
                ref="overview.2",
            )
        )
    registered = facts.first("registry.companies_house")
    if registered:
        v = registered.value
        since = f", incorporated {v['incorporated']}" if v.get("incorporated") else ""
        overview.append(
            DraftClaim(
                ClaimClass.FACT,
                f"Registered with Companies House as {v['name']} ({v['number']}), "
                f"status {v['status']}{since}.",
                [registered.evidence_id],
                subject="company.registry",
                ref="overview.registry",
                confidence=registered.confidence,
            )
        )
    accounts = facts.first("registry.accounts")
    if accounts and accounts.value.get("made_up_to"):
        kind = str(accounts.value["type"]).replace("-", " ")
        overview.append(
            DraftClaim(
                ClaimClass.FACT,
                f"Latest accounts filed: {kind}, made up to {accounts.value['made_up_to']}.",
                [accounts.evidence_id],
                subject="company.size",
                ref="overview.accounts",
                confidence=accounts.confidence,
            )
        )
    sections["company_overview"] = Section(
        overview, unknown=None if overview else "Company details Unknown."
    )

    problems: list[DraftClaim] = []
    problem_ref: dict[int, str] = {}
    chosen: list[Candidate] = []
    for candidate in [*inputs.candidates[:3], *(m.candidate for m in inputs.matches)]:
        if all(candidate is not c for c in chosen):
            chosen.append(candidate)
    for i, candidate in enumerate(chosen):
        ref = f"problem.{i}"
        problem_ref[id(candidate)] = ref
        problems.append(
            DraftClaim(
                ClaimClass.INFERENCE,
                candidate.problem,
                list(candidate.evidence_ids),
                subject=f"opportunity.{candidate.category}",
                ref=ref,
                confidence=candidate.confidence,
            )
        )
    sections["problem_detected"] = Section(
        problems, unknown=None if problems else "No commercial opportunity was detected."
    )

    rejected = inputs.assessment.icp.hard_reject
    reject_note = f"Not applicable: rejected ({inputs.assessment.icp.rejection_reason})."
    primary = (
        None
        if rejected
        else next((m for m in inputs.matches if m.slot == ServiceSlot.PRIMARY), None)
    )
    why: list[DraftClaim] = []
    if primary:
        text = f"{primary.service.name} fits the strongest need found: {lower_first(primary.candidate.title)}."
        if inputs.similarity:
            text += f" It resembles Verkies' work for {inputs.similarity.project}."
        why.append(
            DraftClaim(
                ClaimClass.RECOMMENDATION,
                text,
                [],
                [problem_ref[id(primary.candidate)]],
                subject="why_verkies",
                ref="why_verkies.0",
            )
        )
    sections["why_verkies"] = Section(
        why,
        unknown=None
        if why
        else reject_note
        if rejected
        else "No Verkies service matches the evidence yet.",
    )

    now: list[DraftClaim] = []
    roles = facts.first("hiring.tech_roles")
    if roles:
        now.append(
            DraftClaim(
                ClaimClass.FACT,
                f"Hiring now: {', '.join(roles.value[:3])}.",
                [roles.evidence_id],
                subject="why_now.hiring",
                ref="why_now.0",
            )
        )
    waitlist = facts.first("product.waitlist")
    if waitlist:
        now.append(
            DraftClaim(
                ClaimClass.FACT,
                "Running a pre-launch waitlist.",
                [waitlist.evidence_id],
                subject="why_now.launch",
                ref="why_now.1",
            )
        )
    now += _signal_claims(facts)
    sections["why_now"] = Section(now, unknown=None if now else "No time-bound signal found.")

    services: list[DraftClaim] = []
    for i, match in enumerate([] if rejected else inputs.matches):
        services.append(
            DraftClaim(
                ClaimClass.RECOMMENDATION,
                f"{SLOT_LABEL[match.slot]}: {match.service.name}, for {lower_first(match.candidate.title)}.",
                [],
                [problem_ref[id(match.candidate)]],
                subject=f"service.{match.slot.value}",
                ref=f"service.{i}",
                confidence=match.confidence,
            )
        )
    sections["recommended_service"] = Section(
        services,
        unknown=None
        if services
        else reject_note
        if rejected
        else "No confirmed Verkies service matches.",
    )

    buyer = decision_maker(facts)
    buyer_claims: list[DraftClaim] = []
    if buyer is not None:
        title = buyer.value.get("title")
        buyer_claims.append(
            DraftClaim(
                ClaimClass.FACT,
                f"{buyer.value['name']}" + (f", {title}." if title else "."),
                [buyer.evidence_id],
                subject="buyer",
                ref="buyer.0",
                confidence=buyer.confidence,
            )
        )
    sections["best_buyer"] = Section(
        buyer_claims,
        unknown=None
        if buyer_claims
        else "No named decision maker found on the site or in the register.",
    )

    sections["similar_project"] = (
        Section(notes=[f"{inputs.similarity.project}: {inputs.similarity.because}"])
        if inputs.similarity
        else Section(unknown="Unknown: no complete reference-project profile to compare yet.")
    )

    angle: list[DraftClaim] = []
    if primary and primary.candidate.category in SALES_ANGLES:
        who = _audience(facts)
        angle.append(
            DraftClaim(
                ClaimClass.RECOMMENDATION,
                SALES_ANGLES[primary.candidate.category].format(who=who),
                [],
                [problem_ref[id(primary.candidate)]],
                subject="sales_angle",
                ref="angle.0",
            )
        )
    sections["sales_angle"] = Section(
        angle,
        unknown=None
        if angle
        else reject_note
        if rejected
        else "No sales angle without a matched need.",
    )

    a = inputs.assessment
    risks = [h.note for h in a.icp.hits if h.severity in ("soft", "review")]
    risks += [f"Not qualified: {r}." for r in a.not_qualified_because]
    unknown = a.breakdown.get("unknown", [])
    if unknown:
        risks.append("Unknown: " + ", ".join(u.replace("_", " ") for u in unknown) + ".")
    sections["risks"] = Section(notes=risks, unknown=None if risks else "No specific risks found.")

    sections["next_action"] = _next_action(inputs, problems, buyer_claims)
    return Draft(sections)


def _audience(facts: Facts) -> str:
    industries = [
        f.value["name"] for f in facts.all("company.industry") if f.value.get("basis") == "keywords"
    ]
    industries = industries or [f.value["name"] for f in facts.all("company.industry")]
    return f"{industries[0]} firms" if industries else "firms like theirs"


def _next_action(
    inputs: BriefInputs, problems: list[DraftClaim], buyer: list[DraftClaim]
) -> Section:
    a = inputs.assessment
    if a.icp.hard_reject:
        return Section(unknown=f"Do not contact: rejected ({a.icp.rejection_reason}).")
    if not problems:
        return Section(unknown="Research further: no evidenced need yet.")
    focus = problems[0]
    topic = lower_first(inputs.candidates[0].title) if inputs.candidates else "their main need"
    if a.qualifies and buyer:
        name = buyer[0].text.split(",")[0].rstrip(".")
        text = f"Look up {name} on LinkedIn and send a short note about {topic}."
        supports = [buyer[0].ref, focus.ref]
    elif a.qualifies:
        text = f"Find the decision maker, then send a short note about {topic}."
        supports = [focus.ref]
    else:
        reason = a.not_qualified_because[0] if a.not_qualified_because else "missing information"
        text = f"Research further before contacting ({reason})."
        supports = [focus.ref]
    return Section(
        [
            DraftClaim(
                ClaimClass.RECOMMENDATION,
                text,
                [],
                supports,
                subject="next_action",
                ref="next_action.0",
            )
        ]
    )


PRIORITY_JOBS = ("cto_hiring", "developer_hiring", "product_hiring")


def _signal_claims(facts: Facts) -> list[DraftClaim]:
    """Dated buying signals from the company's job board and its own news feed. The wording
    only repeats what each cited posting or headline says (titles, board, dates)."""
    claims: list[DraftClaim] = []
    postings = facts.all("signal.job_posting")
    by_board: dict[str, list[Fact]] = {}
    for fact in postings:
        by_board.setdefault(str(fact.value.get("provider")), []).append(fact)
    for n, (provider, group) in enumerate(sorted(by_board.items())):
        # Newest first, then technology and product roles ahead of the rest (stable sorts).
        group.sort(key=lambda f: str(f.value.get("published") or ""), reverse=True)
        group.sort(key=lambda f: f.value.get("signal") not in PRIORITY_JOBS)
        shown = group[:3]
        titles = "; ".join(str(f.value["title"]) for f in shown)
        ids = [f.evidence_id for f in shown]
        dated = [f for f in group if f.value.get("published")]
        latest = max(dated, key=lambda f: str(f.value["published"])) if dated else None
        text = f"Hiring now on {PROVIDER_NAMES.get(provider, provider)}: {titles}"
        if latest is not None:
            text += f" (latest posted {latest.value['published']})"
            if latest.evidence_id not in ids:
                ids.append(latest.evidence_id)
        claims.append(
            DraftClaim(
                ClaimClass.FACT,
                text + ".",
                ids,
                subject="why_now.job_postings",
                ref=f"why_now.jobs.{n}",
            )
        )
    filings = sorted(
        facts.all("signal.filing"), key=lambda f: str(f.value.get("published")), reverse=True
    )
    for n, fact in enumerate(filings[:2]):
        claims.append(
            DraftClaim(
                ClaimClass.FACT,
                f"Companies House, {fact.value['published']}: {fact.value['title']}.",
                [fact.evidence_id],
                subject=f"why_now.{fact.value.get('signal')}",
                ref=f"why_now.filing.{n}",
            )
        )
    news = sorted(
        facts.all("signal.news"), key=lambda f: str(f.value.get("published")), reverse=True
    )
    for n, fact in enumerate(news[:2]):
        claims.append(
            DraftClaim(
                ClaimClass.FACT,
                f"{fact.value['published']}: {fact.value['title'].rstrip('.')}.",
                [fact.evidence_id],
                subject=f"why_now.{fact.value.get('signal')}",
                ref=f"why_now.news.{n}",
            )
        )
    return claims
