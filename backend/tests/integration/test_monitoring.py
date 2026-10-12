"""Slices 6.1 and 6.2: watchlists, monitoring checks, alerts and website changes."""

import asyncio
import hashlib
import json
import uuid
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings
from app.monitoring import service as monitoring
from app.monitoring.router import get_check_enqueuer
from app.providers.errors import ProviderError
from app.providers.fetch.types import DEFAULT_CONTENT_TYPES, FetchResult
from app.providers.storage import LocalStorage
from app.registry.stage import Registries
from app.research.source import CachedPageSource
from app.signals.jobs import JobBoards
from tests.integration.conftest import ApiClient, make_user
from tests.integration.test_leads import account

pytestmark = pytest.mark.integration

BOARD = "https://boards-api.greenhouse.io/v1/boards/acme/jobs"


class FakeSource:
    """Stands in for the web: what each URL answers. Anything else cannot be reached."""

    budget = SimpleNamespace(content_types=DEFAULT_CONTENT_TYPES)

    def __init__(self, responses: dict[str, tuple[int, str, str]]) -> None:
        self.responses = responses

    async def fetch(self, url: str, *, content_types: frozenset[str] | None = None) -> FetchResult:
        if url not in self.responses:
            raise ProviderError("unreachable", code="fetch_failed")
        status, ctype, body = self.responses[url]
        return FetchResult(url, url, status, {"content-type": ctype}, ctype, body.encode())


def board(*titles: str) -> dict[str, tuple[int, str, str]]:
    jobs = [
        {
            "title": t,
            "absolute_url": f"https://boards.greenhouse.io/acme/jobs/{i}",
            "location": {"name": "London"},
            "first_published": "2026-10-01T09:00:00Z",
        }
        for i, t in enumerate(titles)
    ]
    return {BOARD: (200, "application/json", json.dumps({"jobs": jobs}))}


def researched(
    engine: Engine,
    owner: uuid.UUID,
    *,
    seen: str | None = None,
    pages: dict[str, tuple[str, str]] | None = None,
    storage: LocalStorage | None = None,
) -> uuid.UUID:
    """An account whose completed research found a Greenhouse board (and, optionally, a posting
    and the pages it read: URL -> (category, HTML), the first being the homepage)."""
    acme = account(engine, "Acme Legal", domain="acme.test", owner=owner)
    run_id = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO research_runs (id, input_url, normalised_domain, requested_by_id,"
                " status, review_status, retry_count, crawl_budget, possible_duplicate_of,"
                " account_id, finished_at) VALUES (:id, 'https://acme.test/', 'acme.test', :u,"
                " 'completed', 'approved', 0, '{}', '[]', :a, now())"
            ),
            {"id": run_id, "u": owner, "a": acme},
        )
        facts: list[tuple[str, str, dict[str, Any]]] = [
            ("hiring", "hiring.job_board", {"provider": "greenhouse", "token": "acme"})
        ]
        if seen:
            facts.append(
                (
                    "signals",
                    "signal.job_posting",
                    {
                        "signal": "developer_hiring",
                        "title": seen,
                        "url": "https://boards.greenhouse.io/acme/jobs/0",
                        "published": "2026-10-01",
                    },
                )
            )
        for area, key, value in facts:
            evidence_id = uuid.uuid4()
            conn.execute(
                text(
                    "INSERT INTO evidence (id, research_run_id, source_url, source_domain,"
                    " collected_at, evidence_type, evidence_text, content_hash, confidence)"
                    " VALUES (:id, :r, 'https://acme.test/careers', 'acme.test', now(),"
                    " 'page_content', 'Careers', 'h', 0.9)"
                ),
                {"id": evidence_id, "r": run_id},
            )
            conn.execute(
                text(
                    "INSERT INTO observations (id, research_run_id, attempt, area, key, value,"
                    " evidence_id, seen_on, confidence) VALUES (gen_random_uuid(), :r, 0, :area,"
                    " :key, CAST(:v AS jsonb), :e, '[]', 0.9)"
                ),
                {"r": run_id, "area": area, "key": key, "v": json.dumps(value), "e": evidence_id},
            )
        for i, (url, (category, html)) in enumerate((pages or {}).items()):
            assert storage is not None
            body = html.encode()
            raw_id = uuid.uuid4()
            conn.execute(
                text(
                    "INSERT INTO raw_responses (id, url, final_url, rendered, fetched_at,"
                    " status_code, headers, body_ref, content_type, bytes, content_hash)"
                    " VALUES (:id, :url, :url, false, now() - interval '7 days', 200, '{}', :ref,"
                    " 'text/html', :n, :h)"
                ),
                {
                    "id": raw_id,
                    "url": url,
                    "ref": storage.put(body),
                    "n": len(body),
                    "h": hashlib.sha256(body).hexdigest(),
                },
            )
            conn.execute(
                text(
                    "INSERT INTO research_pages (id, research_run_id, kind, url, final_url,"
                    " discovered_via, category, status_code, content_type, bytes,"
                    " raw_response_id, from_cache, rendered)"
                    " VALUES (gen_random_uuid(), :r, 'page', :url, :url, :via, :cat, 200,"
                    " 'text/html', :n, :raw, false, false)"
                ),
                {
                    "r": run_id,
                    "url": url,
                    "via": "start" if i == 0 else "link",
                    "cat": category,
                    "n": len(body),
                    "raw": raw_id,
                },
            )
    return acme


def check(
    account_id: uuid.UUID, web: FakeSource, storage: LocalStorage | None = None
) -> monitoring.CheckResult:
    async def run() -> monitoring.CheckResult:
        engine = create_async_engine(get_settings().database_url)
        try:
            sessionmaker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
            store = storage or LocalStorage(Path(get_settings().storage_dir) / "monitor-tests")
            deps = monitoring.MonitorDeps(
                sessionmaker=sessionmaker,
                # As the worker builds it: always fresh, and every read kept for next time.
                source=CachedPageSource(
                    sessionmaker=sessionmaker,
                    storage=store,
                    fetcher=web,  # type: ignore[arg-type]
                    renderer=None,
                    cache_days=0,
                    force_refresh=True,
                ),
                fetcher=None,  # type: ignore[arg-type] - the registries are disabled
                boards=JobBoards.default(),
                registries=Registries.disabled(),
                storage=store,
            )
            return await monitoring.check_account(account_id, deps)
        finally:
            await engine.dispose()

    return asyncio.run(run())


@pytest.fixture
def admin(engine: Engine, api: ApiClient) -> uuid.UUID:
    user_id = make_user(engine, "ada@verkies.test", ["admin"], name="Ada Admin")
    api.login("ada@verkies.test")
    return user_id


def test_watching_an_account(engine: Engine, api: ApiClient, admin: uuid.UUID) -> None:
    acme = researched(engine, admin)
    assert api.get(f"/accounts/{acme}").json()["watching"] is False
    assert api.send("PUT", f"/accounts/{acme}/watch").status_code == 204
    api.send("PUT", f"/accounts/{acme}/watch")  # twice is still once
    body = api.get(f"/accounts/{acme}").json()
    assert body["watching"] is True and body["watchers"] == 1
    watched = api.get("/monitoring/watched").json()
    assert [(w["name"], w["watching"], w["last_checked_at"]) for w in watched] == [
        ("Acme Legal", True, None)
    ]
    assert api.send("DELETE", f"/accounts/{acme}/watch").status_code == 204
    assert api.get("/monitoring/watched").json() == []


def test_a_check_alerts_only_on_what_is_new(
    engine: Engine, api: ApiClient, admin: uuid.UUID
) -> None:
    acme = researched(engine, admin, seen="Senior Backend Engineer")
    api.send("PUT", f"/accounts/{acme}/watch")

    first = check(acme, FakeSource(board("Senior Backend Engineer", "Head of Product")))
    assert first.checked and first.read == 2 and first.new == 1  # the engineer was seen in research
    alerts = api.get("/monitoring/alerts").json()
    assert [(a["title"], a["kind"], a["signal"], a["signal_label"]) for a in alerts] == [
        ("Head of Product", "job_posting", "product_hiring", "Hiring for product")
    ]
    assert alerts[0]["happened_on"] == "2026-10-01" and not alerts[0]["reviewed"]

    second = check(acme, FakeSource(board("Senior Backend Engineer", "Head of Product", "CTO")))
    assert second.new == 1
    assert [a["title"] for a in api.get("/monitoring/alerts").json()] == ["CTO", "Head of Product"]

    events = [e["summary"] for e in api.get(f"/accounts/{acme}/timeline").json()]
    assert "Monitoring found 1 new signal: Hiring for product." in events
    assert "Monitoring found 1 new signal: Hiring a CTO." in events
    assert api.get("/monitoring/watched").json()[0]["last_checked_at"] is not None

    reviewed = api.send("POST", f"/monitoring/alerts/{alerts[0]['id']}/review").json()
    assert reviewed["reviewed"] is True
    assert len(api.get("/monitoring/alerts", params={"open": True}).json()) == 1

    # Monitoring checks are not research: not listed, not on the account, not in review.
    assert all(
        r["normalised_domain"] != "acme.test" or r["review_status"] != "not_required"
        for r in api.get("/research-runs").json()
    )
    assert len(api.get(f"/accounts/{acme}").json()["research_runs"]) == 1


def test_a_failing_source_is_reported_not_silent(
    engine: Engine, api: ApiClient, admin: uuid.UUID
) -> None:
    acme = researched(engine, admin)
    result = check(acme, FakeSource({}))
    assert result.checked and result.new == 0
    assert result.errors and result.errors[0].startswith("greenhouse")
    with engine.connect() as conn:
        error = conn.execute(
            text("SELECT error FROM research_runs WHERE kind = 'monitor' AND account_id = :a"),
            {"a": acme},
        ).scalar_one()
    assert error and "greenhouse" in error


def test_nothing_to_check_without_research(engine: Engine, admin: uuid.UUID) -> None:
    bare = account(engine, "Bare Co", domain="bare.test", owner=admin)
    result = check(bare, FakeSource({}))
    assert not result.checked and result.reason == "no completed research to know its sources"


def test_check_now_and_who_sees_what(
    engine: Engine, api: ApiClient, admin: uuid.UUID, make_api: Callable[[], ApiClient]
) -> None:
    acme = researched(engine, admin)
    queued: list[tuple[uuid.UUID, uuid.UUID]] = []
    api.http.app.dependency_overrides[get_check_enqueuer] = lambda: (
        lambda a, u: queued.append((a, u))
    )  # type: ignore[attr-defined]
    assert api.send("POST", f"/accounts/{acme}/monitor/check").status_code == 202
    assert queued == [(acme, admin)]

    check(acme, FakeSource(board("Head of Product")))
    make_user(engine, "sam@verkies.test", ["salesperson"], name="Sam Seller")
    seller = make_api()
    seller.login("sam@verkies.test")
    assert seller.get("/monitoring/alerts").json() == []  # Ada's account
    assert seller.send("PUT", f"/accounts/{acme}/watch").status_code == 404
    assert seller.send("POST", f"/accounts/{acme}/monitor/check").status_code == 404


HOME = "https://acme.test/"
SERVICES = "https://acme.test/services"
ABOUT = "https://acme.test/about"


def html(body: str, head: str = "") -> str:
    return f"<html><head><title>Acme</title>{head}</head><body>{body}</body></html>"


HOME_BEFORE = html(
    '<a href="/services">Services</a> <a href="/about">About us</a>'
    "<h1>Acme Legal</h1><p>Immigration solicitors in Manchester since 2009.</p>"
)
SERVICES_BEFORE = html(
    "<h1>Services</h1><p>We help with spouse visas, skilled worker visas and appeals."
    " Fixed fees are agreed before any work starts.</p>"
)


ABOUT_BEFORE = html("<h1>About us</h1><p>Founded by two solicitors.</p>")


def site() -> dict[str, tuple[int, str, str]]:
    """The site as research read it."""
    return {
        HOME: (200, "text/html", HOME_BEFORE),
        SERVICES: (200, "text/html", SERVICES_BEFORE),
        ABOUT: (200, "text/html", ABOUT_BEFORE),
    }


def watched_site(engine: Engine, admin: uuid.UUID, storage: LocalStorage) -> uuid.UUID:
    pages = {
        HOME: ("home", HOME_BEFORE),
        SERVICES: ("services", SERVICES_BEFORE),
        ABOUT: ("about", ABOUT_BEFORE),
    }
    return researched(engine, admin, pages=pages, storage=storage)


def test_website_changes_are_reported_with_before_and_after(
    engine: Engine, api: ApiClient, admin: uuid.UUID, tmp_path: Path
) -> None:
    storage = LocalStorage(tmp_path)
    acme = watched_site(engine, admin, storage)
    api.send("PUT", f"/accounts/{acme}/watch")

    # Nothing changed: nothing to report.
    same = check(acme, FakeSource(site()), storage)
    assert same.checked and same.changes == 0
    assert [a for a in api.get("/monitoring/alerts").json() if a["kind"] == "website"] == []

    changed = site()
    changed[HOME] = (
        200,
        "text/html",
        html(
            '<a href="/services">Services</a> <a href="/pricing">Pricing</a>'
            "<h1>Acme Legal</h1><p>Immigration solicitors in Manchester since 2009.</p>",
            '<script src="https://widget.intercom.io/widget/abc"></script>',
        ),
    )
    changed[SERVICES] = (
        200,
        "text/html",
        html(
            "<h1>Services</h1><p>We help with spouse visas, skilled worker visas, appeals and"
            " citizenship. Fixed fees are agreed before any work starts.</p>"
        ),
    )
    result = check(acme, FakeSource(changed), storage)
    assert result.checked and result.errors == ["greenhouse: unreachable"]  # no board here
    alerts = {a["title"]: a for a in api.get("/monitoring/alerts").json() if a["kind"] == "website"}
    assert set(alerts) == {
        "New page linked from the homepage: Pricing",
        "No longer linked from the homepage: About us",
        "Homepage changed",
        "Services page changed",
        "Live chat added: Intercom",
    }
    services = alerts["Services page changed"]["detail"]
    assert services["change"] == "page_changed" and services["topic"] == "services"
    assert "appeals. Fixed fees" in services["before"]
    assert "appeals and citizenship." in services["after"]
    assert services["before_url"] == SERVICES and services["before_seen_at"]
    pricing = alerts["New page linked from the homepage: Pricing"]
    assert pricing["source_url"] == "https://acme.test/pricing"
    assert pricing["detail"]["topic"] == "pricing"
    chat = alerts["Live chat added: Intercom"]["detail"]
    assert chat["topic"] == "contact" and "widget.intercom.io" in chat["after"]
    events = [e["summary"] for e in api.get(f"/accounts/{acme}/timeline").json()]
    assert any(e.startswith("Monitoring found 5 website changes:") for e in events)

    # The changed pages are now what VROS last saw: reading them again reports nothing new.
    again = check(acme, FakeSource(changed), storage)
    assert again.changes == 0


def test_a_missing_page_is_a_removal_but_an_unreachable_one_is_not(
    engine: Engine, api: ApiClient, admin: uuid.UUID, tmp_path: Path
) -> None:
    storage = LocalStorage(tmp_path)
    acme = watched_site(engine, admin, storage)
    web = site()
    web[SERVICES] = (404, "text/html", "")
    del web[ABOUT]  # cannot be reached at all
    result = check(acme, FakeSource(web), storage)
    assert result.changes == 1
    assert any(e.startswith(f"{ABOUT}: ") for e in result.errors)
    (alert,) = [a for a in api.get("/monitoring/alerts").json() if a["kind"] == "website"]
    assert alert["title"] == "Services page removed (now answers 404)"
    assert alert["detail"]["topic"] == "services"
    assert "spouse visas" in alert["detail"]["before"]
