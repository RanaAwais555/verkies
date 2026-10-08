"""Lead brief: service matching, similarity, template brief, grounding and AI mode."""

import json
from typing import Any

import httpx
import pytest

from app.briefs.claims import DraftClaim
from app.briefs.grounding import Evidence, ungrounded_terms, validate
from app.briefs.template import BriefInputs, build, evidence_index, vocabulary
from app.briefs.writer import write_brief
from app.catalogue.defaults import SERVICES, solved_by
from app.catalogue.matching import ServiceInfo, match_services
from app.core.enums import ClaimClass, ServiceSlot
from app.intelligence.facts import facts_from_observations
from app.intelligence.runner import analyse
from app.opportunities.detectors import Candidate, detect
from app.providers.ai import NullAIProvider, OllamaProvider
from app.providers.errors import ProviderError, ProviderUnavailable
from app.qualification.config import IcpConfigModel
from app.scoring.config import ScoringConfigModel
from app.scoring.engine import assess
from app.similarity.engine import ReferenceProfile, best, compare
from tests.fixtures.sites import AGENCY, HOLDING, IMMIGRATION, SAAS

CATALOGUE = [ServiceInfo(k, n, tuple(s)) for k, n, s, _ in SERVICES]


def inputs_for(
    fixture: tuple[Any, Any], references: list[ReferenceProfile] | None = None
) -> BriefInputs:
    facts = facts_from_observations(analyse(*fixture)[0])
    candidates = detect(facts)
    matches = match_services(candidates, CATALOGUE)
    refs = references or []
    sims = [
        compare(
            r,
            industries=[f.value["name"] for f in facts.all("company.industry")],
            problems=[c.problem for c in candidates],
            matches=matches,
        )
        for r in refs
    ]
    return BriefInputs(
        facts,
        candidates,
        matches,
        best(sims),
        assess(
            facts,
            candidates,
            solved_by=solved_by(),
            icp_config=IcpConfigModel(),
            scoring_config=ScoringConfigModel(),
        ),
        [r.name for r in refs] or ["Wesbridge Associates"],
    )


# --- service matching ---------------------------------------------------------------------


def test_matching_gives_up_to_three_distinct_evidenced_services() -> None:
    inputs = inputs_for(IMMIGRATION)
    slots = [(m.slot, m.service.key) for m in inputs.matches]
    assert slots == [
        (ServiceSlot.PRIMARY, "web_dev"),
        (ServiceSlot.SECONDARY, "crm_portal"),
        (ServiceSlot.EXPANSION, "seo_content"),
    ]
    assert len({k for _, k in slots}) == len(slots) <= 3
    for match in inputs.matches:
        assert match.candidate.evidence_ids and match.candidate.category in match.service.solves


def test_secondary_needs_enough_confidence_and_nothing_without_candidates() -> None:
    weak = [
        Candidate("website_rebuild", "A", "p", 0.8, "r", ["e"]),
        Candidate("crm", "B", "p", 0.45, "r", ["e"]),
    ]
    matches = match_services(weak, CATALOGUE)
    assert [m.slot for m in matches] == [ServiceSlot.PRIMARY, ServiceSlot.EXPANSION]
    assert match_services([], CATALOGUE) == []


# --- similarity ---------------------------------------------------------------------------

WESBRIDGE = ReferenceProfile(
    "Wesbridge Associates",
    "UK immigration advice (IAA-regulated)",
    "Broken WordPress site; enquiries answered by email; manual intake; letters assembled by hand.",
    ("web_dev", "seo_content", "crm_portal", "public_tools"),
    profile_complete=True,
)


def test_incomplete_reference_profiles_are_unknown() -> None:
    inputs = inputs_for(IMMIGRATION)
    incomplete = ReferenceProfile(**{**WESBRIDGE.__dict__, "profile_complete": False})
    result = compare(incomplete, industries=["immigration"], problems=["x"], matches=inputs.matches)
    assert result.score is None and "Unknown" in result.because


def test_complete_profile_compares_problems_services_and_industry() -> None:
    inputs = inputs_for(IMMIGRATION, [WESBRIDGE])
    assert inputs.similarity is not None
    assert inputs.similarity.project == "Wesbridge Associates"
    assert (inputs.similarity.score or 0) > 50
    assert (
        "same industry" in inputs.similarity.because
        and "same services" in inputs.similarity.because
    )


# --- grounding validator ------------------------------------------------------------------

EVIDENCE = {
    "e1": Evidence(
        "e1", "Harbour Immigration Ltd, 1 Cheapside, London. Call 020 7946 0001. © 2017", "u"
    ),
    "e2": Evidence("e2", "No online booking tool found on 4 crawled pages", "u"),
}
VOCAB = {"Verkies", "Harbour Immigration Ltd", "CRM, practice systems and client portals"}


@pytest.mark.parametrize(
    ("text", "invented"),
    [
        ("Harbour raised £2m last year.", "£2m"),
        ("They employ 45 people.", "45"),
        ("Their CEO John Smith is the buyer.", "John Smith"),
        ("Email jo@harbour.example to start.", "jo@harbour.example"),
        ("See https://harbour.example/fees for prices.", "https://harbour.example/fees"),
        ("They are a Salesforce customer.", "Salesforce"),
    ],
)
def test_invented_entities_are_caught(text: str, invented: str) -> None:
    assert invented in " ".join(ungrounded_terms(text, EVIDENCE["e1"].excerpt, VOCAB))
    kept, dropped = validate([DraftClaim(ClaimClass.FACT, text, ["e1"], ref="x")], EVIDENCE, VOCAB)
    assert kept == [] and "does not show" in dropped[0]["reason"]


def test_grounded_claims_survive() -> None:
    claims = [
        DraftClaim(
            ClaimClass.FACT,
            "Harbour Immigration Ltd is in London; call 020 7946 0001.",
            ["e1"],
            ref="a",
        ),
        DraftClaim(
            ClaimClass.INFERENCE,
            "With no online booking, consultations are arranged by hand.",
            ["e2"],
            ref="b",
        ),
        DraftClaim(
            ClaimClass.RECOMMENDATION,
            "Propose CRM, practice systems and client portals.",
            [],
            ["b"],
            ref="c",
        ),
    ]
    kept, dropped = validate(claims, EVIDENCE, VOCAB)
    assert [c.ref for c in kept] == ["a", "b", "c"] and dropped == []


@pytest.mark.parametrize(
    ("claim", "reason"),
    [
        (DraftClaim(ClaimClass.FACT, "They are in London.", [], ref="x"), "no evidence cited"),
        (DraftClaim(ClaimClass.FACT, "They are in London.", ["e99"], ref="x"), "does not exist"),
        (
            DraftClaim(
                ClaimClass.INFERENCE, "Verkies will help your business grow.", ["e2"], ref="x"
            ),
            "generic filler",
        ),
        (
            DraftClaim(ClaimClass.RECOMMENDATION, "Pitch a CRM.", [], ["nope"], ref="x"),
            "rests on no",
        ),
        (DraftClaim(ClaimClass.INFERENCE, "  ", ["e1"], ref="x"), "empty"),
    ],
)
def test_ungrounded_claims_are_dropped_with_reason(claim: DraftClaim, reason: str) -> None:
    kept, dropped = validate([claim], EVIDENCE, VOCAB)
    assert kept == [] and reason in dropped[0]["reason"]


# --- template brief -----------------------------------------------------------------------


@pytest.mark.parametrize("fixture", [IMMIGRATION, SAAS, HOLDING, AGENCY])
async def test_template_brief_is_fully_grounded(fixture: tuple[Any, Any]) -> None:
    inputs = inputs_for(fixture)
    draft, generated_by = await write_brief(inputs, NullAIProvider())
    assert generated_by["mode"] == "template" and generated_by["dropped"] == []
    known = set(evidence_index(inputs.facts))
    refs = {c.ref for c in draft.claims()}
    for claim in draft.claims():
        if claim.claim_class in (ClaimClass.FACT, ClaimClass.INFERENCE):
            assert claim.evidence_ids and set(claim.evidence_ids) <= known, claim
        else:
            assert claim.supports and set(claim.supports) <= refs, claim
    for name, section in draft.sections.items():
        assert section.claims or section.unknown or section.notes, name  # never silently empty


async def test_brief_content_for_service_firm() -> None:
    draft, _ = await write_brief(inputs_for(IMMIGRATION), NullAIProvider())
    s = draft.sections
    assert s["best_buyer"].claims[0].text == "Amelia Hart, Founder and Senior Immigration Adviser."
    assert s["why_now"].unknown == "No time-bound signal found."
    assert "Unknown" in (s["similar_project"].unknown or "")
    assert s["next_action"].claims[0].text.startswith("Look up Amelia Hart on LinkedIn")
    assert s["recommended_service"].claims[0].text.startswith("Primary: Web Development")


async def test_rejected_prospect_gets_no_pitch() -> None:
    draft, _ = await write_brief(inputs_for(AGENCY), NullAIProvider())
    for name in ("why_verkies", "recommended_service", "sales_angle"):
        assert draft.sections[name].claims == [] and "rejected" in (
            draft.sections[name].unknown or ""
        )
    assert draft.sections["next_action"].unknown == "Do not contact: rejected (competitor)."


async def test_similar_project_appears_only_with_a_complete_profile() -> None:
    draft, _ = await write_brief(inputs_for(IMMIGRATION, [WESBRIDGE]), NullAIProvider())
    assert "Wesbridge Associates" in draft.sections["similar_project"].notes[0]
    assert (
        "resembles Verkies' work for Wesbridge Associates"
        in draft.sections["why_verkies"].claims[0].text
    )


# --- AI mode ------------------------------------------------------------------------------


class FakeAI:
    name, model = "fake", "fake-1"

    def __init__(self, output: dict[str, Any] | Exception) -> None:
        self.output = output
        self.prompts: list[str] = []

    async def generate_json(
        self, *, system: str, prompt: str, schema: dict[str, Any]
    ) -> dict[str, Any]:
        self.prompts.append(prompt)
        if isinstance(self.output, Exception):
            raise self.output
        return self.output


def _e(prompt: str, key: str) -> str:
    """The short evidence ID the prompt gave an observation key."""
    line = next(l for l in prompt.splitlines() if f"] {key} =" in l)
    return line.split("]")[0].lstrip("[")


async def test_ai_sections_replace_template_when_grounded() -> None:
    inputs = inputs_for(IMMIGRATION)
    probe = FakeAI({})
    await write_brief(inputs, probe)
    name_id = _e(probe.prompts[0], "company.name")
    address_id = _e(probe.prompts[0], "company.address")
    ai = FakeAI(
        {
            "company_overview": [
                {
                    "class": "fact",
                    "text": "Harbour Immigration Ltd advises on UK visas from London.",
                    "evidence": [name_id, address_id],
                }
            ],
            "why_verkies": [
                {
                    "class": "recommendation",
                    "text": "Their manual intake is the kind of process Verkies rebuilds as a client portal.",
                    "supports": ["P2"],
                }
            ],
            "why_now": [],
            "sales_angle": [],
        }
    )
    draft, generated_by = await write_brief(inputs, ai)
    assert generated_by["mode"] == "ai" and generated_by["ai_sections"] == [
        "company_overview",
        "why_verkies",
    ]
    overview = draft.sections["company_overview"]
    assert overview.source == "ai" and overview.claims[0].evidence_ids[0] in evidence_index(
        inputs.facts
    )
    assert draft.sections["sales_angle"].source == "template"  # empty AI section: template kept
    assert "<evidence>" in ai.prompts[0] and "</evidence>" in ai.prompts[0]


async def test_hallucinating_model_is_contained() -> None:
    inputs = inputs_for(IMMIGRATION)
    probe = FakeAI({})
    await write_brief(inputs, probe)
    name_id = _e(probe.prompts[0], "company.name")
    ai = FakeAI(
        {
            "company_overview": [
                {
                    "class": "fact",
                    "text": "Harbour Immigration Ltd raised £3m in 2025 and has 60 staff.",
                    "evidence": [name_id],
                },
                {
                    "class": "fact",
                    "text": "Their CEO Mark Jensen wants a CRM.",
                    "evidence": [name_id],
                },
                {"class": "fact", "text": "They use HubSpot.", "evidence": ["E999"]},
            ],
            "why_verkies": [
                {
                    "class": "recommendation",
                    "text": "Verkies can take their business to the next level.",
                    "supports": ["P1"],
                }
            ],
            "why_now": [{"class": "fact", "text": "They just won an award.", "evidence": []}],
            "sales_angle": [
                {"class": "recommendation", "text": "Mention their Series A.", "supports": ["P7"]}
            ],
        }
    )
    draft, generated_by = await write_brief(inputs, ai)
    assert generated_by["mode"] == "template" and generated_by["ai_sections"] == []
    ai_drops = [
        d for d in generated_by["dropped"] if d["source"] == "ai" and d["ref"].startswith("ai.")
    ]
    assert len(ai_drops) == 6
    reasons = " ".join(d["reason"] for d in ai_drops)
    for marker in (
        "£3m",
        "Mark Jensen",
        "does not exist",
        "generic filler",
        "no evidence cited",
        "rests on no",
    ):
        assert marker in reasons
    text = " ".join(c.text for c in draft.claims())
    assert "Mark Jensen" not in text and "£3m" not in text


async def test_ai_failure_falls_back_to_template() -> None:
    draft, generated_by = await write_brief(inputs_for(SAAS), FakeAI(ProviderUnavailable("down")))
    assert generated_by["mode"] == "template" and generated_by["ai_error"] == "down"
    assert draft.sections["why_now"].claims  # template content intact


async def test_ollama_provider_request_and_errors() -> None:
    seen: list[dict[str, Any]] = []

    def ok(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(200, json={"message": {"content": json.dumps({"why_now": []})}})

    provider = OllamaProvider(
        base_url="http://ollama:11434",
        model="m",
        num_ctx=8192,
        timeout_seconds=5,
        transport=httpx.MockTransport(ok),
    )
    assert await provider.generate_json(system="s", prompt="p", schema={"type": "object"}) == {
        "why_now": []
    }
    assert seen[0]["options"]["num_ctx"] == 8192 and seen[0]["format"] == {"type": "object"}
    assert seen[0]["stream"] is False

    bad = OllamaProvider(
        base_url="http://o",
        model="m",
        num_ctx=4096,
        timeout_seconds=5,
        transport=httpx.MockTransport(
            lambda r: httpx.Response(200, json={"message": {"content": "nope"}})
        ),
    )
    with pytest.raises(ProviderError):
        await bad.generate_json(system="s", prompt="p", schema={})

    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    gone = OllamaProvider(
        base_url="http://o",
        model="m",
        num_ctx=4096,
        timeout_seconds=5,
        transport=httpx.MockTransport(down),
    )
    with pytest.raises(ProviderUnavailable):
        await gone.generate_json(system="s", prompt="p", schema={})


def test_template_build_is_deterministic() -> None:
    a = build(inputs_for(IMMIGRATION))
    b = build(inputs_for(IMMIGRATION))
    assert [c.text for c in a.claims()] == [c.text for c in b.claims()]
    assert vocabulary(inputs_for(IMMIGRATION)) >= {"Verkies", "Harbour Immigration Ltd"}
