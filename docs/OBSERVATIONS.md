# VROS Observation Catalogue

What the extract stage records about a company's website (slice 1.3, master context §8). Each observation is one row in `observations` with a `key`, a JSON `value`, a `confidence` and exactly one `evidence` row: source URL, a short excerpt, the evidence type and the collection time. `seen_on` lists every crawled page where the same fact appeared.

**Rules**

- Only what the pages show. Nothing is inferred about the business here; turning observations into opportunities, ICP fit and scores is slice 1.4.
- **Absence** is recorded only where it matters for selling (no enquiry form, no booking tool, no live chat, no pricing page, no structured data) and always at lower confidence (0.6-0.8), with `seen_on` listing the pages that were checked. "Not found on the pages we crawled" is not the same as "does not exist".
- A key missing from a run means the signal was not looked for or not found; it is **Unknown**, not false.
- Observations are append-only. A retried run writes a new `attempt`; the API shows the latest.
- Code: `backend/app/intelligence/extractors/`. Tests against fixture sites: `backend/tests/unit/test_extractors.py`.

API: `GET /api/v1/research-runs/{id}/intelligence` returns the latest attempt's observations grouped by area, each with its evidence.

## Website (technical health)

| Key | Value | Notes |
| --- | --- | --- |
| `website.https` | bool | Homepage final URL is https |
| `website.hsts` | bool | `Strict-Transport-Security` header on the homepage |
| `website.security_headers` | `{present: [...], missing: [...]}` | CSP, X-Frame-Options, X-Content-Type-Options, Referrer-Policy |
| `website.mobile_viewport` | bool | `<meta name="viewport">` on the homepage |
| `website.homepage_html_kb` | number | HTML only, not images or scripts; omitted for rendered pages |
| `website.robots_txt` | `parsed` / `missing` / `unreachable` | From the crawl |
| `website.sitemap` | bool | A sitemap was found and read |
| `website.broken_internal_links` | list of URLs | Links on crawled pages to same-site pages that returned 4xx/5xx |
| `website.copyright_year` | int | Latest year in the homepage copyright line |
| `website.stale_copyright` | int (years behind) | Copyright year two or more years old; a weak staleness signal |
| `website.last_modified` | string | `Last-Modified` header, if sent |

## SEO

| Key | Value |
| --- | --- |
| `seo.home_title` | `{text, length, in_range}` (15-65 chars) or null |
| `seo.home_meta_description` | `{text, length, in_range}` (50-165 chars) or null |
| `seo.home_h1` | text or null |
| `seo.home_canonical` | URL or null |
| `seo.pages_missing_title`, `seo.pages_missing_meta_description`, `seo.pages_without_h1`, `seo.pages_with_multiple_h1` | list of URLs (only when non-empty) |
| `seo.structured_data_types` | list of top-level JSON-LD `@type`s (empty list = none found) |
| `seo.open_graph` | bool |
| `seo.noindex_pages` | list of URLs |
| `seo.image_alt_coverage` | `{images, with_alt, ratio}` across crawled pages |
| `seo.home_word_count` | int |
| `seo.hreflang` | list of language codes |

## Conversion

| Key | Value |
| --- | --- |
| `conversion.contact_form` | bool (search and newsletter forms excluded) |
| `conversion.contact_form_fields` | e.g. `["name", "email", "phone", "message"]` |
| `conversion.newsletter_signup` | true |
| `conversion.email_addresses`, `conversion.phone_numbers` | lists from `mailto:` / `tel:` links |
| `conversion.whatsapp` | true |
| `conversion.booking_tool` | vendor name (Calendly, Acuity, Cal.com, HubSpot Meetings, ...) or null |
| `conversion.live_chat` | vendor name (Intercom, Drift, Crisp, Tawk.to, Zendesk, HubSpot Chat, ...) or null |
| `conversion.reviews_widget` | vendor name (Trustpilot, Feefo, REVIEWS.io, ...) |
| `conversion.home_ctas` | list of call-to-action texts on the homepage (empty = none) |
| `conversion.primary_cta` | first call to action on the homepage |
| `conversion.testimonials` | true |
| `conversion.trust_signals` | e.g. `["IAA-regulated", "ISO 27001", "award-winning"]` |
| `conversion.pricing_page` | bool |
| `conversion.case_studies_page` | true |

## Product

| Key | Value |
| --- | --- |
| `product.login`, `product.signup` | URL of the sign-in / sign-up link |
| `product.app_store_links` | list of App Store / Google Play URLs |
| `product.api_docs` | URL |
| `product.portal` | matched phrase (client portal, dashboard, ...) |
| `product.subscription_pricing` | matched phrase (per month, billed annually, ...) |
| `product.online_tool` | matched phrase (calculator, instant quote, eligibility checker, ...) |
| `product.site_search` | true |
| `product.payments` | list of payment providers (Stripe, PayPal, GoCardless, ...) |

## Technology

| Key | Value |
| --- | --- |
| `technology.detected` | `{name, category}`, one per technology; evidence is the exact marker (generator tag, script URL, header or HTML snippet) |
| `technology.generator` | the `<meta name="generator">` value |

About 40 rules in `extractors/technology.py`, covering the technologies the master context names (WordPress, WooCommerce, Shopify, Wix, Squarespace, Webflow, Elementor, React, Next.js, Vue, Angular, PHP, Drupal, Magento, ...) plus analytics, marketing, payments, hosting and servers. Importing the full community Wappalyzer rule set is a later improvement.

## Company

| Key | Value |
| --- | --- |
| `company.name` | og:site_name (0.85), JSON-LD organisation name (0.85) or the `<title>` prefix (0.5) |
| `company.description` | meta description or og:description |
| `company.address` | JSON-LD PostalAddress fields |
| `company.country_hint` | ISO country from the phone prefix (0.7) or the domain's country TLD (0.6). A hint for the ICP engine, not a fact about headquarters |
| `company.social_profiles` | `{linkedin, x, facebook, instagram, youtube, github, tiktok}` (share links ignored) |
| `company.linkedin_company_url` | URL |
| `company.founded_year` | int ("founded in", "established", "since") |
| `company.person` | `{name, title}` from JSON-LD Person (0.85) or a name heading followed by a role on team/about pages (0.6). Feeds Contacts on approval (slice 1.6) |

## Hiring

| Key | Value |
| --- | --- |
| `hiring.careers_page` | true |
| `hiring.job_board` | `{provider, token, url}` for Greenhouse, Lever, Ashby, Workable, Teamtailor, BambooHR, Recruitee, Workday, Personio. The token is what the Phase 2 job-board APIs need |
| `hiring.tech_roles` | engineering/product role titles on the careers page |

Feeds are found by the company extractor: `company.feed` is `{url, format}` for an RSS or Atom `<link rel="alternate">` on the company's own site (at most two, comment feeds ignored).

## Signals (slice 2.2, the `signals` stage)

Dated buying signals (master context §9), read only from sources the company's own site points to.

| Key | Value | Evidence |
| --- | --- | --- |
| `signal.job_posting` | `{signal, provider, title, location, department, url, published}`. `signal` is `developer_hiring`, `cto_hiring`, `product_hiring` or `hiring` | `job_posting`: "Title (Location) — posted DATE on Board"; `published_at` set when the board gives a date |
| `signal.news` | `{signal, title, url, published}`. `signal` is `funding`, `acquisition`, `new_leader`, `expansion`, `new_service` or `product_launch` | `news_item`: "Headline — published DATE"; confidence 0.75, because a headline keyword is not a confirmed event |

Rules:
- **Job postings:** come from the public APIs of Greenhouse, Lever, Ashby and Workable, and only for the board the site links to. At most 50 per board.
- **News:** comes from the company's own feed, fetched under its robots.txt. An item is kept only if its headline clearly names a signal type and it is dated within the last 365 days. At most 10.
- **Failures:** a board or feed that fails is listed in the stage's `errors` and never fails the run.

## Registry (slice 2.3, the `enrich` stage)

Found on the site by the company extractor: `company.registration_number` is `{number, jurisdiction}`. It is the registered number UK companies must print on their site (e.g. "Company number 06812345", "Registered in England and Wales No. SC123456"), normalised to the Companies House form.

| Key | Value | Evidence |
| --- | --- | --- |
| `registry.companies_house` | `{number, name, status, active, incorporated, type, sic_codes, locality, postal_code}` | `company_registry`, citing the public Companies House page; confidence 0.95 |
| `registry.officer` | `{name, role, appointed, number}`: current directors and LLP members only | the company's officers page; confidence 0.95 |
| `registry.wikidata` | `{qid, label, inception, employees, country, industries}` | the Wikidata item; confidence 0.8 |

When each source is used:
- **Companies House:** looked up only by the registered number, never by a name search. The record is kept only if its name shares a distinctive word with the site's name or domain.
- **Wikidata:** used only when exactly one item gives this domain as its official website.

Added in slice 2.5 (filing history and the PSC register):

| Key | Value | Evidence |
| --- | --- | --- |
| `registry.accounts` | `{type, size_band, made_up_to, filed}`. The size band comes from the accounts type: micro-entity → micro; small, abridged or total exemption → small; medium; full; group; dormant | the filing-history page |
| `registry.owner` | `{name, natures, notified, number}`: current individual persons with significant control | the PSC page |
| `signal.filing` (area `signals`) | `{signal, title, published}` for filings in the last 365 days: director appointed → `new_leader`; change of name → `rebrand`; share allotment → `funding`; charge registered → `financing` | the filing-history page, dated |

Where the facts go:
- **Contacts:** officers join site people. The same person, matched by first and last name, counts once. Officers count as named decision makers.
- **ICP:** an inactive status triggers the `closed` rule. An insolvency history, or dormant accounts, flag the prospect for review without rejecting it.
- **Scores:** the accounts size band adjusts Commercial Potential. Filing events feed Intent and Timing like other dated signals.
- **People:** owners count as named decision makers.
- **The brief:** the company overview cites the registration.
- **Approval:** stores `account_identifiers` (companies_house, wikidata). A later run with the same identifier joins that account even under another domain.

## Site status and industry

| Key | Value | Notes |
| --- | --- | --- |
| `website.holding_page` | `parked` or `coming_soon` | Parked/for-sale wording, or a short page saying coming soon / under construction |
| `company.closed_notice` | phrases | "ceased trading", "permanently closed", "we have closed" |
| `company.personal_site_signals` | phrases | "hire me", "my portfolio", "freelance web developer", "download my CV" |
| `company.agency_signals` | phrases | "digital agency", "we build websites for", "white-label services", "our clients include" |
| `product.waitlist` | phrases | "join the waitlist", "early access", "private beta" |
| `company.industry` | `{name, basis, hits?}` | Keyword rules or a JSON-LD type; Unknown unless clear (ICP_SPEC.md §3) |

These feed the negative-ICP rules and the pre-launch (MVP) detector; an ordinary business site produces none of the first five.

## Not yet observed (and why)

- **Lighthouse performance/accessibility scores** need Chrome and a full page load per audit; planned with the worker's Chromium as a separate, optional stage.
- **TLS certificate expiry, MX/SPF/DMARC** need DNS and TLS lookups; planned behind the `DnsChecker` provider (PROVIDER_SPEC.md §3).
- **Company registry facts, funding, news** are Phase 2 providers.
