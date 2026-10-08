"""Web search discovery: results to candidate companies, and the SearXNG client."""

import httpx
import pytest

from app.discovery.web_search import candidates, company_name
from app.providers.errors import ProviderError, ProviderUnavailable
from app.providers.search import NullSearchProvider, SearchResult, SearxngProvider


def _r(url: str, title: str = "Acme Ltd | Software", snippet: str = "s") -> SearchResult:
    return SearchResult(title, url, snippet)


def test_results_become_one_candidate_per_company_site() -> None:
    rows = candidates(
        [
            _r("https://www.harbour.test/visas/spouse", "Harbour Immigration | Spouse visas"),
            _r("https://harbour.test/contact", "Contact | Harbour"),  # same site again
            _r("https://uk.linkedin.com/company/harbour", "Harbour | LinkedIn"),
            _r("https://www.yell.com/biz/harbour", "Harbour - Yell"),
            _r("https://www.gov.uk/visas", "Visas - GOV.UK"),
            _r("https://immigration.blog.example.ac.uk/x", "Uni blog"),
            _r("ftp://files.test/x", "FTP"),
            _r("https://shiplane.test/", "Home | Shiplane", "Logistics software"),
        ]
    )
    assert rows == [
        {
            "name": "Harbour Immigration",
            "website": "https://www.harbour.test/",
            "notes": "s",
            "source_url": "https://www.harbour.test/visas/spouse",
        },
        {
            "name": "Shiplane",
            "website": "https://shiplane.test/",
            "notes": "Logistics software",
            "source_url": "https://shiplane.test/",
        },
    ]


@pytest.mark.parametrize(
    ("title", "name"),
    [
        ("Harbour Immigration | UK Visa Advisers", "Harbour Immigration"),
        ("Welcome - Old Mill Bakery", "Old Mill Bakery"),
        ("Acme \u2013 Software for fleets", "Acme"),
        ("Plain", "Plain"),
        ("", None),
    ],
)
def test_titles_give_a_name_label(title: str, name: str | None) -> None:
    assert company_name(title) == name


def _searxng(pages: dict[int, list[dict[str, object]]], status: int = 200) -> SearxngProvider:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        page = int(request.url.params["pageno"])
        return httpx.Response(status, json={"results": pages.get(page, [])})

    provider = SearxngProvider(
        "http://searxng:8080/", timeout_seconds=5, transport=httpx.MockTransport(handler)
    )
    provider.seen = seen  # type: ignore[attr-defined]
    return provider


async def test_searxng_reads_pages_until_empty_and_asks_for_json() -> None:
    provider = _searxng(
        {
            1: [{"url": "https://a.test/", "title": "A", "content": "first", "engine": "brave"}],
            2: [{"url": "https://b.test/", "title": "B"}, {"title": "no url"}],
        }
    )
    results = await provider.search("bakeries leeds", pages=3, language="en-GB")
    assert [r.url for r in results] == ["https://a.test/", "https://b.test/"]
    assert results[0].snippet == "first" and results[0].engine == "brave"
    requests = provider.seen  # type: ignore[attr-defined]
    assert len(requests) == 3  # page 3 was empty: stop
    first = requests[0].url
    assert first.path == "/search" and first.params["format"] == "json"
    assert first.params["q"] == "bakeries leeds" and first.params["language"] == "en-GB"


async def test_searxng_errors_are_reported_not_hidden() -> None:
    with pytest.raises(ProviderError, match="JSON format"):
        await _searxng({}, status=403).search("x")

    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    broken = SearxngProvider(
        "http://searxng:8080", timeout_seconds=5, transport=httpx.MockTransport(down)
    )
    with pytest.raises(ProviderUnavailable):
        await broken.search("x")
    with pytest.raises(ProviderUnavailable, match="not set up"):
        await NullSearchProvider().search("x")


def test_candidate_websites_keep_ports_but_never_credentials() -> None:
    (row,) = candidates([_r("https://user:secret@acme.test:8443/about", "Acme")])
    assert row["website"] == "https://acme.test:8443/"


def test_register_names_become_search_names() -> None:
    from app.discovery.websites import search_name

    assert search_name("BRIGHT LEGAL LTD") == "Bright Legal"
    assert search_name("QUIET FIRM LIMITED") == "Quiet Firm"
    assert search_name("Acme Holdings PLC") == "Acme Holdings"
