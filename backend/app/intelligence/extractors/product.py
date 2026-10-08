"""Signs of a software product or customer-facing system (master context §8, Product row)."""

import re

from app.intelligence.html import links, script_sources
from app.intelligence.types import Area, Observation, Page, SiteContext, excerpt

LOGIN = re.compile(
    r"^(log ?in|sign ?in|client login|customer login|member login|my account)$", re.I
)
SIGNUP = re.compile(
    r"^(sign ?up|register|create (?:an |your )?account|start (?:your )?free trial|"
    r"get started(?: free| for free)?|try (?:it )?(?:for )?free)$",
    re.I,
)
PORTAL = re.compile(
    r"\b(client portal|customer portal|member portal|partner portal|dashboard)\b", re.I
)
SUBSCRIPTION = re.compile(
    r"(per month|/\s?mo(?:nth)?\b|per user|billed (?:annually|monthly|yearly)|"
    r"monthly plan|annual plan)",
    re.I,
)
TOOLS = re.compile(
    r"\b(\w+ calculator|instant quote|quote calculator|eligibility (?:check(?:er)?|tool)|"
    r"price estimator|cost estimator)\b",
    re.I,
)
PAYMENTS = {
    "js.stripe.com": "Stripe",
    "paypal.com/sdk": "PayPal",
    "gocardless": "GoCardless",
    "checkout.com": "Checkout.com",
    "squareup.com": "Square",
}


def extract(pages: list[Page], ctx: SiteContext) -> list[Observation]:
    out: list[Observation] = []

    def obs(key: str, value: object, page: Page, text: str, **kw: object) -> None:
        out.append(Observation(Area.PRODUCT, f"product.{key}", value, page.url, text, **kw))  # type: ignore[arg-type]

    found: dict[str, tuple[str, Page, str]] = {}
    app_stores: list[str] = []
    for page in pages:
        for url, text, _ in links(page):
            low = url.lower()
            if "login" not in found and LOGIN.match(text):
                found["login"] = (url, page, f'Link "{text}" → {url}')
            if "signup" not in found and SIGNUP.match(text):
                found["signup"] = (url, page, f'Link "{text}" → {url}')
            if (
                "apps.apple.com" in low or "play.google.com/store" in low
            ) and url not in app_stores:
                app_stores.append(url)
                found.setdefault("app_store", (url, page, f"App store link: {url}"))
            if (
                "api_docs" not in found
                and re.search(r"\bapi\b", text, re.I)
                and ("/api" in low or "developer" in low or "docs" in low)
            ):
                found["api_docs"] = (url, page, f'Link "{text}" → {url}')
    for key in ("login", "signup", "api_docs"):
        if key in found:
            url, page, text = found[key]
            obs(key, url, page, text)
    if app_stores:
        _, page, text = found["app_store"]
        obs("app_store_links", app_stores, page, text)

    for key, pattern in (
        ("portal", PORTAL),
        ("subscription_pricing", SUBSCRIPTION),
        ("online_tool", TOOLS),
    ):
        hit = next(((p, m) for p in pages if (m := pattern.search(p.text))), None)
        if hit:
            page, match = hit
            obs(key, match.group(0), page, excerpt(page.text, match.group(0)), confidence=0.75)

    search = next(
        (p for p in pages if p.tree.css_first('input[type="search"], form[role="search"]')), None
    )
    if search:
        obs("site_search", True, search, "Search box present", confidence=0.85)

    for page in pages:
        sources = " ".join(script_sources(page)).lower() + page.html.lower()
        names = [name for marker, name in PAYMENTS.items() if marker in sources]
        if names:
            obs(
                "payments",
                names,
                page,
                f"Payment provider scripts: {', '.join(names)}",
                confidence=0.85,
            )
            break
    return out
