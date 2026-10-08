# VROS Provider Specification

Implements §18 and §18A. External services never appear in business logic. Each is reached through an interface in `app/providers/`, selected by settings, replaceable, and optional. **No paid provider is required.**

## 1. Contract for every provider

- Async-capable, typed request/response models (Pydantic).
- Raises `ProviderUnavailable` (service down, not configured) or `ProviderError` (bad response); callers degrade, never crash the run.
- Declares its rate limit; the worker enforces it with a per-source limiter in Redis.
- Returns **evidence-ready** results: every fact carries `source_url` and `collected_at`.
- Responses are cached as `raw_responses` and reused until stale.
- Has a fake implementation used in all tests. No test makes a network call.

## 2. Interfaces

```python
class Fetcher(Protocol):
    async def fetch(self, url: str, *, budget: FetchBudget) -> FetchResult: ...
    # FetchResult: final_url, status, headers, body (bounded), content_type, redirects, elapsed_ms

class AIProvider(Protocol):
    async def generate_json(self, *, task: str, prompt: str, schema: dict, model_hint: str) -> dict: ...
    async def generate_text(self, *, prompt: str, model_hint: str) -> str: ...

class EmbeddingProvider(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]: ...

class SearchProvider(Protocol):
    async def search(self, query: DiscoveryQuery) -> list[CompanyCandidate]: ...

class CompanyDataProvider(Protocol):
    async def lookup(self, ref: CompanyRef) -> CompanyFacts: ...
    async def watch(self, refs: list[CompanyRef]) -> AsyncIterator[CompanyEvent]: ...

class Storage(Protocol):
    def put(self, key: str, data: bytes, *, content_type: str) -> None: ...
    def get(self, key: str) -> bytes: ...

class EmailProvider(Protocol): ...      # Phase 3: send, list_threads, read_reply
class CalendarProvider(Protocol): ...   # Phase 3
```

## 3. Free sources by phase (§18A)

Order of use: official API or structured feed first, crawling second.

| Source | Interface | Phase | Limit / note | Cache |
| --- | --- | --- | --- | --- |
| Target website (httpx + lxml) | `Fetcher` | 1 | Robots-aware, per-domain concurrency 2 | 7 days |
| Playwright Chromium | `Fetcher` | 1 | Only when static fetch is thin | 7 days |
| Lighthouse CLI | `WebsiteAudit` | 1 (homepage + one key page) | Subprocess, timeout, queue-limited | 7 days |
| Wappalyzer community rules | local matcher | 1 | No API; rules vendored with licence note | n/a |
| `ssl`, `dnspython` (MX, SPF, DMARC) | `DnsChecker` | 1 | | 1 day |
| CSV import | `SearchProvider` | 2 | | n/a |
| Companies House API + bulk data | `CompanyDataProvider` | 2 | 600 req / 5 min; streaming API for watched companies | 30 days |
| SEC EDGAR (Form D) | `CompanyDataProvider` | 2 | Descriptive User-Agent required | 30 days |
| Wikidata SPARQL | `CompanyDataProvider` | 2 | | 30 days |
| Greenhouse, Lever, Ashby, Workable public job APIs | `SignalProvider` | 2 | Keyless JSON | 1 day |
| Google News RSS, company blog/press RSS | `SignalProvider` | 2 | | 1 day |
| SearXNG (self-hosted) | `SearchProvider` | 2 | Low request rate | 1 day |
| Common Crawl index | `SearchProvider` | 2 (batch) | | n/a |
| Gmail API, Microsoft Graph, IMAP/SMTP | `EmailProvider` | 3 | Free with existing accounts | n/a |
| Ollama | `AIProvider`, `EmbeddingProvider` | 1 | Local | n/a |

**Not used:** LinkedIn scraping or automation, paid enrichment (Apollo, Hunter, Clearbit, Crunchbase), SMTP mailbox probing, and anything that bypasses CAPTCHAs, logins or paywalls (§18A).

## 4. Fetcher budget (Phase 1)

Defaults, all configurable per run and bounded by global maximums:

| Limit | Default |
| --- | --- |
| Max pages | 15 |
| Max bytes per response | 2 MB |
| Max total bytes | 15 MB |
| Max redirects | 5 |
| Request timeout | 15 s |
| Per-domain concurrency | 2, with ≥ 1 s spacing |
| Run wall-clock | 120 s |
| Content types accepted | `text/html`, `application/xhtml+xml`, `text/plain`, `application/xml` (sitemap), `application/json` (structured feeds) |

The crawler identifies itself as `VROSBot/<version> (+<contact URL>)` (`VROS_CRAWLER_CONTACT_URL`), normalises and de-duplicates URLs (tracking parameters dropped), records canonical duplicates, and never submits forms, logs in or solves challenges. A 403/429 ends the crawl of that domain and is recorded as a limitation, not retried around.

**robots.txt** follows RFC 9309: a 200 is parsed (`VROSBot` or `*` rules, `Crawl-delay` honoured up to 10 s); a 4xx means no rules; a 5xx or unreachable robots.txt means do not crawl. Disallowed pages are recorded with `skip_reason = robots_disallowed`.

**What is fetched:** robots.txt, the homepage, up to 4 sitemaps (following a sitemap index), then the highest-value same-site pages from homepage links and sitemap entries: about, team, services, product, pricing, contact, careers, account (login/signup/portal), work (case studies, clients) and blog, at most two per category, homepage links before sitemap entries, shallow paths first. Keywords match whole words of the path and link text. Pages whose static HTML has under 400 characters of text, or an empty app root (`#root`, `#__next`, `#app`), are rendered with JavaScript; if rendering is unavailable the static HTML is kept.

**Cache:** each fetch is stored in `raw_responses` (body in storage, content-addressed) and reused for `VROS_CRAWL_CACHE_DAYS` (default 7) when it was a 200; rendered pages are cached separately. Every page a run fetched, reused, skipped or was refused is recorded in `research_pages` with the reason.

Settings: `VROS_CRAWL_MAX_PAGES`, `VROS_CRAWL_MAX_BYTES_PER_RESPONSE`, `VROS_CRAWL_MAX_TOTAL_BYTES`, `VROS_CRAWL_MAX_REDIRECTS`, `VROS_CRAWL_REQUEST_TIMEOUT_SECONDS`, `VROS_CRAWL_WALL_CLOCK_SECONDS`, `VROS_CRAWL_MIN_INTERVAL_SECONDS`, `VROS_CRAWL_CONCURRENCY`, `VROS_CRAWL_ALLOWED_PORTS`, `VROS_RENDER_ENABLED`, `VROS_CHROMIUM_EXECUTABLE`, `VROS_STORAGE_DIR`.

## 5. Provider health

`GET /api/v1/system/providers` reports each provider as `ok`, `degraded` or `unavailable` with the reason. The UI shows degraded modes (for example "AI unavailable: briefs use template mode").

## 6. Swapping a provider

A new implementation needs: the interface, a settings entry, a fake, contract tests shared by real and fake implementations, and a line in this document. Business logic changes are not required, and a change that needs one is a bug in the interface.
