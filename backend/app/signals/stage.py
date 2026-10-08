"""Signals stage (master context §9 buying signals; ARCHITECTURE.md §5).

Reads what the extract stage found on the company's own site (links to a job board, RSS/Atom
feed links) and collects dated signals from those sources only: the board's public API and the
company's own feeds. Every signal is an observation in the `signals` area with its evidence
(source URL, excerpt, published date). A source that fails is reported, never fatal, and an
item without a clear type or date is left out rather than guessed.
"""

import json
import uuid
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.enums import EvidenceType, ObservationArea
from app.intelligence.facts import Facts
from app.intelligence.stage import persist_observation
from app.intelligence.types import Observation
from app.providers.errors import ProviderError
from app.research.crawler import ROBOTS_TYPES, PageSource
from app.research.models import ResearchRun
from app.research.robots import RobotsPolicy
from app.scoring.stage import load_facts
from app.signals import classify, feeds, jobs

MAX_POSTINGS = 50
MAX_NEWS = 10
NEWS_WINDOW_DAYS = 365
JSON_TYPES = frozenset({"application/json"})
FEED_TYPES = frozenset(
    {"application/rss+xml", "application/atom+xml", "application/xml", "text/xml"}
)


def _midnight(day: date | None) -> datetime | None:
    return datetime.combine(day, time(), tzinfo=UTC) if day else None


def posting_observation(posting: jobs.JobPosting, api_url: str) -> Observation:
    board = jobs.PROVIDER_NAMES.get(posting.provider, posting.provider)
    where = f" ({posting.location})" if posting.location else ""
    when = f"posted {posting.published.isoformat()}" if posting.published else "open"
    return Observation(
        ObservationArea.SIGNALS,
        "signal.job_posting",
        {
            "signal": classify.job_signal(posting.title),
            "provider": posting.provider,
            "title": posting.title,
            "location": posting.location,
            "department": posting.department,
            "url": posting.url,
            "published": posting.published.isoformat() if posting.published else None,
        },
        posting.url or api_url,
        f"{posting.title}{where} — {when} on {board}",
        evidence_type=EvidenceType.JOB_POSTING,
        confidence=0.9,
        published_at=_midnight(posting.published),
    )


def news_observation(item: feeds.FeedItem, kind: str, feed_url: str) -> Observation:
    assert item.published is not None
    return Observation(
        ObservationArea.SIGNALS,
        "signal.news",
        {
            "signal": kind,
            "title": item.title,
            "url": item.url,
            "published": item.published.isoformat(),
        },
        item.url or feed_url,
        f"{item.title} — published {item.published.isoformat()}",
        evidence_type=EvidenceType.NEWS_ITEM,
        confidence=0.75,  # a headline keyword, not a confirmed event
        published_at=_midnight(item.published),
    )


async def robots_for(source: PageSource, url: str) -> RobotsPolicy:
    parts = urlsplit(url)
    try:
        fetched = await source.fetch(
            f"{parts.scheme}://{parts.netloc}/robots.txt", content_types=ROBOTS_TYPES
        )
    except ProviderError:
        return RobotsPolicy.deny_all("unreachable")
    return RobotsPolicy.from_response(fetched.result.status, fetched.result.text())


async def collect(
    facts: Facts, source: PageSource, boards: jobs.JobBoards, today: date
) -> tuple[list[Observation], dict[str, Any]]:
    """Observations from every board and feed the facts point at, plus a report."""
    found: list[Observation] = []
    errors: list[str] = []
    boards_read: list[str] = []
    seen: set[tuple[str, str]] = set()
    for fact in facts.all("hiring.job_board"):
        provider, token = str(fact.value.get("provider")), str(fact.value.get("token"))
        api = boards.url(provider, token)
        if api is None or (provider, token) in seen:
            continue
        seen.add((provider, token))
        try:
            fetched = await source.fetch(api, content_types=JSON_TYPES)
            if fetched.result.status != 200:
                raise ProviderError(f"HTTP {fetched.result.status}", code="http_error")
            postings = jobs.parse(provider, json.loads(fetched.result.text()))
        except (ProviderError, ValueError) as exc:
            errors.append(f"{provider}: {getattr(exc, 'message', 'invalid JSON')}")
            continue
        boards_read.append(provider)
        found += [posting_observation(p, api) for p in postings[:MAX_POSTINGS]]

    feeds_read: list[str] = []
    news = 0
    cutoff = today - timedelta(days=NEWS_WINDOW_DAYS)
    for fact in facts.all("company.feed"):
        url = str(fact.value.get("url"))
        robots = await robots_for(source, url)
        if not robots.allows(url):
            errors.append(f"feed {url}: disallowed by robots.txt")
            continue
        try:
            fetched = await source.fetch(url, content_types=FEED_TYPES)
            if fetched.result.status != 200:
                raise ProviderError(f"HTTP {fetched.result.status}", code="http_error")
            items = feeds.parse(fetched.result.text())
        except ProviderError as exc:
            errors.append(f"feed {url}: {exc.message}")
            continue
        feeds_read.append(url)
        for item in items:
            kind = classify.news_signal(item.title)
            if kind is None or item.published is None or not cutoff <= item.published <= today:
                continue
            if news >= MAX_NEWS:
                break
            found.append(news_observation(item, kind, url))
            news += 1
    report = {
        "job_boards": boards_read,
        "job_postings": sum(1 for o in found if o.key == "signal.job_posting"),
        "feeds": feeds_read,
        "news": news,
        "errors": errors,
    }
    return found, report


async def signals_stage(
    run_id: uuid.UUID,
    sessionmaker: async_sessionmaker[AsyncSession],
    source: PageSource,
    boards: jobs.JobBoards,
    today: date | None = None,
) -> dict[str, Any]:
    async with sessionmaker() as db:
        run = await db.get(ResearchRun, run_id)
        assert run is not None
        attempt = run.retry_count
        facts = await load_facts(db, run)
    observations, report = await collect(facts, source, boards, today or datetime.now(UTC).date())
    async with sessionmaker() as db:
        for observation in observations:
            persist_observation(db, run_id, attempt, observation)
        await db.commit()
    return report
