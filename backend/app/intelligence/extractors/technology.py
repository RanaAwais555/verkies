"""Technology fingerprints (master context §8, Technology row).

A compact, in-repo rule table in the shape of the community Wappalyzer rules (HTML, script
src, meta generator, headers). Every detection stores the exact marker that matched. Importing
the full community rule set is a later improvement (PROVIDER_SPEC.md §3); this covers the
technologies the master context names.
"""

import re
from dataclasses import dataclass

from app.core.enums import EvidenceType
from app.intelligence.html import meta, script_sources
from app.intelligence.types import Area, Observation, Page, SiteContext


@dataclass(frozen=True)
class Rule:
    name: str
    category: (
        str  # cms, ecommerce, framework, analytics, marketing, payments, hosting, server, language
    )
    html: str | None = None
    script: str | None = None
    generator: str | None = None
    header: tuple[str, str] | None = None  # (header name, regex on value)


RULES: tuple[Rule, ...] = (
    Rule("WordPress", "cms", html=r"/wp-content/|/wp-includes/", generator=r"wordpress"),
    Rule("WooCommerce", "ecommerce", html=r"woocommerce"),
    Rule("Elementor", "cms", html=r"elementor-(?:element|section|widget)|/elementor/"),
    Rule(
        "Shopify", "ecommerce", html=r"cdn\.shopify\.com|Shopify\.theme", header=("x-shopid", r".")
    ),
    Rule(
        "Wix", "cms", html=r"static\.wixstatic\.com|wix-bolt|_wixCssImports", generator=r"wix\.com"
    ),
    Rule(
        "Squarespace",
        "cms",
        html=r"static1\.squarespace\.com|Static\.SQUARESPACE_CONTEXT",
        generator=r"squarespace",
    ),
    Rule("Webflow", "cms", html=r"data-wf-site|data-wf-page", generator=r"webflow"),
    Rule(
        "Drupal",
        "cms",
        html=r"/sites/default/files/|Drupal\.settings",
        generator=r"drupal",
        header=("x-drupal-cache", r"."),
    ),
    Rule("Joomla", "cms", generator=r"joomla"),
    Rule("Magento", "ecommerce", html=r"Mage\.Cookies|/static/version\d+/frontend/|mage/cookies"),
    Rule("Ghost", "cms", generator=r"ghost"),
    Rule(
        "HubSpot CMS",
        "cms",
        html=r"\.hs-sites\.com|hs-sites-|hubspotusercontent",
        generator=r"hubspot",
    ),
    Rule("Framer", "cms", html=r"framerusercontent\.com|data-framer-", generator=r"framer"),
    Rule(
        "Next.js",
        "framework",
        html=r"__NEXT_DATA__|/_next/static/",
        header=("x-powered-by", r"next\.js"),
    ),
    Rule("Nuxt", "framework", html=r"__NUXT__|/_nuxt/"),
    Rule("Gatsby", "framework", html=r"___gatsby"),
    Rule("React", "framework", html=r"data-reactroot|react-dom(?:\.production)?(?:\.min)?\.js"),
    Rule("Vue.js", "framework", html=r"data-v-[0-9a-f]{8}|vue(?:\.runtime)?(?:\.min)?\.js"),
    Rule("Angular", "framework", html=r"ng-version=\"|ng-app=\""),
    Rule("Svelte", "framework", html=r"class=\"[^\"]*svelte-[a-z0-9]{5,}"),
    Rule("jQuery", "library", script=r"jquery(?:[-.]\d[\d.]*)?(?:\.min)?\.js"),
    Rule("Bootstrap", "library", html=r"bootstrap(?:\.min)?\.(?:css|js)"),
    Rule("Ruby on Rails", "framework", html=r"name=\"csrf-param\" content=\"authenticity_token\""),
    Rule("ASP.NET", "framework", html=r"__VIEWSTATE", header=("x-aspnet-version", r".")),
    Rule("PHP", "language", header=("x-powered-by", r"php")),
    Rule("Express", "framework", header=("x-powered-by", r"express")),
    Rule(
        "Google Analytics",
        "analytics",
        script=r"googletagmanager\.com/gtag/js|google-analytics\.com",
    ),
    Rule("Google Tag Manager", "analytics", html=r"googletagmanager\.com/gtm\.js|GTM-[A-Z0-9]{4,}"),
    Rule("Meta Pixel", "marketing", html=r"connect\.facebook\.net/[^\"']*/fbevents\.js"),
    Rule("LinkedIn Insight", "marketing", html=r"snap\.licdn\.com/li\.lms-analytics"),
    Rule("Hotjar", "analytics", html=r"static\.hotjar\.com"),
    Rule("Microsoft Clarity", "analytics", html=r"clarity\.ms/tag"),
    Rule(
        "HubSpot", "marketing", script=r"js\.hs-scripts\.com|js\.hsforms\.net|js\.hs-analytics\.net"
    ),
    Rule("Mailchimp", "marketing", html=r"list-manage\.com|chimpstatic\.com"),
    Rule("Stripe", "payments", script=r"js\.stripe\.com"),
    Rule("Cloudflare", "hosting", header=("server", r"cloudflare")),
    Rule("Vercel", "hosting", header=("x-vercel-id", r".")),
    Rule("Netlify", "hosting", header=("server", r"netlify")),
    Rule("Nginx", "server", header=("server", r"nginx")),
    Rule("Apache", "server", header=("server", r"apache")),
    Rule("Microsoft IIS", "server", header=("server", r"microsoft-iis")),
)


def _match(rule: Rule, page: Page) -> tuple[str, EvidenceType] | None:
    if rule.header:
        name, pattern = rule.header
        value = page.headers.get(name)
        if value and re.search(pattern, value, re.I):
            return f"{name}: {value[:120]}", EvidenceType.HTTP_HEADER
    if rule.generator:
        generator = meta(page, "generator")
        if generator and re.search(rule.generator, generator, re.I):
            return (
                f'<meta name="generator" content="{generator[:120]}">',
                EvidenceType.TECHNOLOGY_FINGERPRINT,
            )
    if rule.script:
        for src in script_sources(page):
            if re.search(rule.script, src, re.I):
                return f'<script src="{src[:200]}">', EvidenceType.TECHNOLOGY_FINGERPRINT
    if rule.html:
        match = re.search(rule.html, page.html, re.I)
        if match:
            start = max(0, match.start() - 60)
            snippet = " ".join(page.html[start : match.end() + 60].split())
            return snippet[:240], EvidenceType.TECHNOLOGY_FINGERPRINT
    return None


def extract(pages: list[Page], ctx: SiteContext) -> list[Observation]:
    out: list[Observation] = []
    for rule in RULES:
        for page in pages:
            hit = _match(rule, page)
            if hit:
                text, kind = hit
                out.append(
                    Observation(
                        Area.TECHNOLOGY,
                        "technology.detected",
                        {"name": rule.name, "category": rule.category},
                        page.url,
                        text,
                        evidence_type=kind,
                        confidence=0.9,
                    )
                )
                break
    generator = next((g for p in pages if (g := meta(p, "generator"))), None)
    if generator:
        page = next(p for p in pages if meta(p, "generator"))
        out.append(
            Observation(
                Area.TECHNOLOGY,
                "technology.generator",
                generator,
                page.url,
                f'<meta name="generator" content="{generator[:120]}">',
                evidence_type=EvidenceType.TECHNOLOGY_FINGERPRINT,
                confidence=0.9,
            )
        )
    return out
