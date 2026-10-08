"""Buying signals: job-board and feed parsing, classification, the stage's collection rules,
their effect on intent and timing, and grounded "Why now" claims."""

from datetime import date, timedelta

import pytest

from app.briefs.grounding import validate
from app.briefs.template import BriefInputs, build, evidence_index, vocabulary
from app.catalogue.defaults import solved_by
from app.catalogue.matching import match_services
from app.intelligence.extractors import feeds as feed_extractor
from app.intelligence.facts import Fact, Facts, facts_from_observations
from app.intelligence.runner import analyse
from app.intelligence.types import Page, SiteContext
from app.opportunities.detectors import detect
from app.providers.errors import ProviderError
from app.providers.fetch.types import FetchResult
from app.qualification.config import IcpConfigModel
from app.research.crawler import Fetched
from app.scoring.config import ScoringConfigModel
from app.scoring.dimensions import intent, timing
from app.scoring.engine import assess
from app.signals import classify, feeds, jobs
from app.signals.stage import collect, news_observation, posting_observation
from tests.fixtures.sites import IMMIGRATION
from tests.unit.test_brief import CATALOGUE

TODAY = date(2026, 10, 8)

GREENHOUSE = {
    "jobs": [
        {
            "id": 1,
            "title": "Senior Backend Engineer",
            "absolute_url": "https://boards.greenhouse.io/shiplane/jobs/1",
            "location": {"name": "London"},
            "departments": [{"name": "Engineering"}],
            "first_published": "2026-09-20T10:00:00Z",
        },
        {"id": 2, "title": "  ", "absolute_url": "https://x"},  # no title: skipped
        {"id": 3, "title": "Office Manager", "updated_at": "not a date"},
    ]
}
LEVER = [
    {
        "text": "Head of Product",
        "hostedUrl": "https://jobs.lever.co/acme/abc",
        "categories": {"location": "Remote", "team": "Product"},
        "createdAt": 1758000000000,
    },
    "garbage",
]
ASHBY = {
    "jobs": [
        {"title": "CTO", "jobUrl": "https://jobs.ashbyhq.com/acme/1", "publishedAt": "2026-08-01"}
    ]
}
WORKABLE = {
    "jobs": [
        {
            "title": "Full Stack Developer",
            "url": "javascript:alert(1)",  # not an http(s) link: dropped
            "city": "Leeds",
            "country": "United Kingdom",
            "published_on": "2026-10-01",
        }
    ]
}


def test_each_board_parses_into_the_same_posting_shape() -> None:
    gh = jobs.parse("greenhouse", GREENHOUSE)
    assert [p.title for p in gh] == ["Senior Backend Engineer", "Office Manager"]
    assert gh[0].location == "London" and gh[0].department == "Engineering"
    assert gh[0].published == date(2026, 9, 20) and gh[1].published is None
    lever = jobs.parse("lever", LEVER)
    assert lever[0].title == "Head of Product" and lever[0].published == date(2025, 9, 16)
    assert jobs.parse("ashby", ASHBY)[0].published == date(2026, 8, 1)
    workable = jobs.parse("workable", WORKABLE)[0]
    assert workable.url is None and workable.location == "Leeds, United Kingdom"
    assert jobs.parse("greenhouse", ["not", "a", "dict"]) == []
    assert jobs.parse("unknown", GREENHOUSE) == []


@pytest.mark.parametrize("token", ["../admin", "a/b", "", "x" * 101, "acme?x=1", "-acme"])
def test_board_tokens_cannot_escape_the_api_path(token: str) -> None:
    assert jobs.JobBoards.default().url("greenhouse", token) is None


def test_only_boards_with_a_public_api_are_queried() -> None:
    boards = jobs.JobBoards.default()
    assert (
        boards.url("greenhouse", "shiplane")
        == "https://boards-api.greenhouse.io/v1/boards/shiplane/jobs"
    )
    assert boards.url("lever", "acme.co") == "https://api.lever.co/v0/postings/acme.co?mode=json"
    assert boards.url("teamtailor", "acme") is None


RSS = """<?xml version="1.0"?><rss version="2.0"><channel><title>Blog</title>
<item><title>Shiplane raises £2m seed round</title><link>https://shiplane.test/blog/seed</link>
<pubDate>Tue, 15 Sep 2026 09:00:00 +0000</pubDate></item>
<item><title>Five tips for dispatchers</title>
<pubDate>Mon, 14 Sep 2026 09:00:00 +0000</pubDate></item>
</channel></rss>"""
ATOM = """<feed xmlns="http://www.w3.org/2005/Atom"><title>News</title>
<entry><title>Introducing Shiplane Mobile</title><link href="https://shiplane.test/news/mobile"/>
<updated>2026-07-01T00:00:00Z</updated></entry></feed>"""


def test_rss_and_atom_feeds_parse() -> None:
    items = feeds.parse(RSS)
    assert items[0] == feeds.FeedItem(
        "Shiplane raises £2m seed round", "https://shiplane.test/blog/seed", date(2026, 9, 15)
    )
    assert feeds.parse(ATOM) == [
        feeds.FeedItem(
            "Introducing Shiplane Mobile", "https://shiplane.test/news/mobile", date(2026, 7, 1)
        )
    ]


@pytest.mark.parametrize(
    "xml",
    [
        '<!DOCTYPE lolz [<!ENTITY lol "lol">]>'
        "<rss><channel><item><title>&lol;</title></item></channel></rss>",
        "<rss><channel><item><title>unclosed",
    ],
)
def test_entity_bombs_and_broken_xml_are_refused(xml: str) -> None:
    with pytest.raises(ProviderError):
        feeds.parse(xml)


@pytest.mark.parametrize(
    ("title", "kind"),
    [
        ("Chief Technology Officer", "cto_hiring"),
        ("Head of Engineering", "cto_hiring"),
        ("Senior Product Manager", "product_hiring"),
        ("Senior Backend Engineer", "developer_hiring"),
        ("Office Manager", "hiring"),
    ],
)
def test_job_titles_map_to_signal_types(title: str, kind: str) -> None:
    assert classify.job_signal(title) == kind


@pytest.mark.parametrize(
    ("title", "kind"),
    [
        ("Shiplane raises £2m seed round", "funding"),
        ("We have acquired RouteCo", "acquisition"),
        ("Acme appoints Jane Doe as CTO", "new_leader"),
        ("Acme opens in Manchester", "expansion"),
        ("Introducing our new service: audits", "new_service"),
        ("Introducing Shiplane Mobile", "product_launch"),
        ("Five tips for dispatchers", None),
    ],
)
def test_headlines_map_to_signal_types_or_nothing(title: str, kind: str | None) -> None:
    assert classify.news_signal(title) == kind


def test_feed_links_are_found_on_the_company_site_only() -> None:
    html = (
        "<html><head>"
        '<link rel="alternate" type="application/rss+xml" title="Blog" href="/feed.xml">'
        '<link rel="alternate" type="application/rss+xml" href="/comments/feed">'
        '<link rel="alternate" type="application/atom+xml" href="https://medium.com/feed/x">'
        "</head><body></body></html>"
    )
    found = feed_extractor.extract(
        [Page("https://shiplane.test/", html, "home")],
        SiteContext("https://shiplane.test/", "missing"),
    )
    assert [o.value for o in found] == [{"url": "https://shiplane.test/feed.xml", "format": "rss"}]


def _fact(key: str, signal: str, published: str | None, n: int = 0) -> Fact:
    return Fact(
        key,
        {"signal": signal, "published": published, "title": "t"},
        0.9,
        f"{key}#{n}",
        "https://x",
    )


def test_intent_follows_the_strongest_signal_and_unknown_without_one() -> None:
    assert intent(Facts([])).score is None
    funding = intent(Facts([_fact("signal.news", "funding", "2026-09-15")]))
    assert funding.score == 85 and funding.evidence_ids == ["signal.news#0"]
    both = intent(
        Facts(
            [
                _fact("signal.news", "funding", "2026-09-15"),
                _fact("signal.job_posting", "developer_hiring", None, 1),
            ]
        )
    )
    assert (
        both.score == 90 and "announced funding" in both.note and "hiring developers" in both.note
    )
    assert intent(Facts([_fact("signal.news", "expansion", "2026-09-15")])).score == 70
    assert intent(Facts([_fact("signal.job_posting", "hiring", "2026-09-15")])).score == 50


@pytest.mark.parametrize(
    ("days_ago", "score"), [(5, 90), (60, 75), (150, 55), (300, 35), (500, None)]
)
def test_timing_decays_with_the_age_of_the_latest_signal(
    days_ago: int, score: float | None
) -> None:
    published = (TODAY - timedelta(days=days_ago)).isoformat()
    assert timing(Facts([_fact("signal.news", "funding", published)]), today=TODAY).score == score


def test_open_postings_without_a_date_count_as_now() -> None:
    dim = timing(Facts([_fact("signal.job_posting", "hiring", None)]), today=TODAY)
    assert dim.score == 75 and "open at the time of research" in dim.note


def test_why_now_signal_claims_survive_grounding() -> None:
    posting = posting_observation(jobs.parse("greenhouse", GREENHOUSE)[0], "https://api")
    news = news_observation(feeds.parse(RSS)[0], "funding", "https://shiplane.test/feed.xml")
    facts = facts_from_observations([*analyse(*IMMIGRATION)[0], posting, news])
    candidates = detect(facts)
    a = assess(
        facts,
        candidates,
        solved_by=solved_by(),
        icp_config=IcpConfigModel(),
        scoring_config=ScoringConfigModel(),
    )
    inputs = BriefInputs(facts, candidates, match_services(candidates, CATALOGUE), None, a, [])
    draft = build(inputs)
    texts = [c.text for c in draft.sections["why_now"].claims]
    assert "Hiring now on Greenhouse: Senior Backend Engineer (latest posted 2026-09-20)." in texts
    assert "2026-09-15: Shiplane raises £2m seed round." in texts
    _, dropped = validate(draft.claims(), evidence_index(facts), vocabulary(inputs))
    assert dropped == []
    assert a.scores["intent_score"] == 90 and a.scores["timing_score"] is not None


class FakeSource:
    def __init__(self, responses: dict[str, tuple[int, str, str]]) -> None:
        self.responses = responses
        self.requested: list[str] = []

    async def fetch(self, url: str, *, content_types: frozenset[str] | None = None) -> Fetched:
        self.requested.append(url)
        if url not in self.responses:
            raise ProviderError("unreachable", code="fetch_failed")
        status, ctype, body = self.responses[url]
        return Fetched(FetchResult(url, url, status, {"content-type": ctype}, ctype, body.encode()))

    async def render(self, url: str) -> Fetched | None:
        return None


async def test_collect_reads_linked_boards_and_feeds_and_reports_failures() -> None:
    import json

    facts = Facts(
        [
            Fact(
                "hiring.job_board",
                {"provider": "greenhouse", "token": "shiplane"},
                0.9,
                "e1",
                "https://shiplane.test/careers",
            ),
            Fact(
                "hiring.job_board",
                {"provider": "greenhouse", "token": "shiplane"},
                0.9,
                "e2",
                "https://shiplane.test/",
            ),
            Fact(
                "hiring.job_board",
                {"provider": "lever", "token": "gone"},
                0.9,
                "e3",
                "https://shiplane.test/",
            ),
            Fact(
                "company.feed",
                {"url": "https://shiplane.test/feed.xml"},
                0.9,
                "e4",
                "https://shiplane.test/",
            ),
            Fact(
                "company.feed",
                {"url": "https://shiplane.test/private/feed.xml"},
                0.9,
                "e5",
                "https://shiplane.test/",
            ),
        ]
    )
    boards = jobs.JobBoards.default()
    source = FakeSource(
        {
            boards.url("greenhouse", "shiplane"): (200, "application/json", json.dumps(GREENHOUSE)),  # type: ignore[dict-item]
            boards.url("lever", "gone"): (404, "application/json", "{}"),  # type: ignore[dict-item]
            "https://shiplane.test/robots.txt": (
                200,
                "text/plain",
                "User-agent: *\nDisallow: /private/",
            ),
            "https://shiplane.test/feed.xml": (200, "application/rss+xml", RSS),
        }
    )
    found, report = await collect(facts, source, boards, TODAY)
    assert report["job_boards"] == ["greenhouse"] and report["job_postings"] == 2
    assert report["feeds"] == ["https://shiplane.test/feed.xml"] and report["news"] == 1
    assert any("lever" in e for e in report["errors"])
    assert any("robots.txt" in e for e in report["errors"])
    assert "https://shiplane.test/private/feed.xml" not in source.requested
    assert source.requested.count(boards.url("greenhouse", "shiplane")) == 1  # queried once
    news = [o for o in found if o.key == "signal.news"]
    assert news[0].value["signal"] == "funding" and news[0].published_at is not None
    assert all(o.area.value == "signals" for o in found)

    old = await collect(facts, source, boards, TODAY + timedelta(days=400))
    assert old[1]["news"] == 0  # announcements older than a year are not signals
