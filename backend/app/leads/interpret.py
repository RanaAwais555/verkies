"""Turns a plain-English request into structured filters (master context §15, slice 2.6).

Deterministic rules, no AI: every phrase is either matched by a rule and shown back to the user
with what it meant, or used as a plain text search and shown as such, or reported as not
supported. Nothing is silently dropped and nothing is guessed. Rules run longest phrase first and
each match is removed from the text, so a word counts once.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

MAX_LIMIT = 200

COUNTRIES: dict[str, tuple[str, str]] = {
    "united kingdom": ("GB", "United Kingdom"),
    "great britain": ("GB", "United Kingdom"),
    "britain": ("GB", "United Kingdom"),
    "british": ("GB", "United Kingdom"),
    "england": ("GB", "United Kingdom"),
    "scotland": ("GB", "United Kingdom"),
    "wales": ("GB", "United Kingdom"),
    "uk": ("GB", "United Kingdom"),
    "ireland": ("IE", "Ireland"),
    "united states": ("US", "United States"),
    "usa": ("US", "United States"),
}

# UK cities people name often; any city already on an account is added from the database.
CITIES = (
    "london", "manchester", "birmingham", "leeds", "liverpool", "bristol", "sheffield",
    "newcastle", "nottingham", "leicester", "cardiff", "edinburgh", "glasgow", "belfast",
    "cambridge", "oxford", "reading", "brighton", "southampton", "york", "milton keynes",
)  # fmt: skip

# phrase -> opportunity category keys (seeded in migration 0003)
CATEGORIES: dict[str, tuple[str, ...]] = {
    "search engine optimisation": ("seo",),
    "search engine optimization": ("seo",),
    "search visibility": ("seo",),
    "seo": ("seo",),
    "conversion": ("conversion_optimization",),
    "converting": ("conversion_optimization",),
    "enquiry form": ("conversion_optimization",),
    "client portals": ("client_portal",),
    "client portal": ("client_portal",),
    "portals": ("client_portal",),
    "portal": ("client_portal",),
    "crm": ("crm",),
    "practice management": ("crm",),
    "product rebuild": ("product_rebuild",),
    "website rebuild": ("website_rebuild",),
    "new website": ("website_rebuild",),
    "redesign": ("website_rebuild",),
    "rebuild": ("product_rebuild", "website_rebuild"),
    "rebuilding": ("product_rebuild", "website_rebuild"),
    "mvp": ("mvp_development",),
    "booking": ("booking_system",),
    "bookings": ("booking_system",),
    "workflow automation": ("workflow_automation",),
    "automation": ("workflow_automation",),
    "mobile app": ("mobile_application",),
    "mobile apps": ("mobile_application",),
    "modernisation": ("application_modernization",),
    "modernization": ("application_modernization",),
    "legacy": ("application_modernization",),
    "integrations": ("integrations",),
    "analytics": ("analytics",),
    "payments": ("payment_workflow",),
    "onboarding": ("customer_onboarding",),
    "internal tools": ("internal_tools",),
    "marketplace": ("marketplace",),
    "technical rescue": ("technical_rescue",),
    "content strategy": ("content_strategy",),
}

HIRING = ("developer_hiring", "cto_hiring", "product_hiring", "hiring")
# Every kind app/signals/classify.py produces (the keys of ranking.SIGNAL_LABELS).
ALL_SIGNALS = (
    *HIRING,
    "funding",
    "financing",
    "product_launch",
    "new_leader",
    "acquisition",
    "expansion",
    "new_service",
    "rebrand",
)
# phrase -> (signal kinds from app/signals/classify.py, what it means)
SIGNALS: dict[str, tuple[tuple[str, ...], str]] = {
    "hiring developers": (("developer_hiring", "cto_hiring"), "Hiring developers"),
    "hiring engineers": (("developer_hiring", "cto_hiring"), "Hiring developers"),
    "developer hiring": (("developer_hiring", "cto_hiring"), "Hiring developers"),
    "hiring a cto": (("cto_hiring",), "Hiring a CTO"),
    "hiring": (HIRING, "Hiring (job postings)"),
    "recruiting": (HIRING, "Hiring (job postings)"),
    "vacancies": (HIRING, "Hiring (job postings)"),
    "raised funding": (("funding",), "Raised funding"),
    "raised": (("funding",), "Raised funding"),
    "funding": (("funding",), "Raised funding"),
    "funded": (("funding",), "Raised funding"),
    "investment": (("funding",), "Raised funding"),
    "launched": (("product_launch",), "Launched a product"),
    "product launch": (("product_launch",), "Launched a product"),
    "expanding": (("expansion",), "Expanding"),
    "expansion": (("expansion",), "Expanding"),
    "new office": (("expansion",), "Expanding"),
    "new ceo": (("new_leader",), "New leadership"),
    "new cto": (("new_leader",), "New leadership"),
    "new leadership": (("new_leader",), "New leadership"),
    "acquired": (("acquisition",), "Acquisition"),
    "acquisition": (("acquisition",), "Acquisition"),
    "rebrand": (("rebrand",), "Rebrand or name change"),
    "buying signals": (ALL_SIGNALS, "Any buying signal"),
    "buying signal": (ALL_SIGNALS, "Any buying signal"),
    "signals": (ALL_SIGNALS, "Any buying signal"),
}

TYPES: dict[str, tuple[tuple[str, ...], str]] = {
    "former customers": (("former_customer",), "Former customers"),
    "past clients": (("former_customer",), "Former customers"),
    "customers": (("customer",), "Customers"),
    "clients": (("customer",), "Customers"),
    "partners": (("partner",), "Partners"),
    "competitors": (("competitor",), "Competitors"),
    "prospects": (("prospect", "qualified_prospect"), "Prospects"),
}

BANDS: dict[str, tuple[tuple[str, ...], str]] = {
    "high priority": (("hot", "high"), "Priority band Hot or High"),
    "hot": (("hot",), "Priority band Hot"),
    "qualified": (("hot", "high", "qualified"), "Priority band Qualified or better"),
}

# Asking for "leads" to contact means the best available prospects, ranked (top-leads mode).
TOP_LEADS = re.compile(
    r"\b(?:next|top|best)\s+(?:(\d{1,3})\s+)?(?:leads?|prospects?|companies|accounts)\b"
    r"|\b(?:should|to)\s+contact\b|\bcontact\s+this\s+week\b|\bmy\s+next\s+leads\b"
)
WINDOW = re.compile(
    r"\b(?:within|in|over)?\s*(?:the\s+)?(?:last|past)\s+(\d{1,3})\s+(day|week|month|year)s?\b"
)
SIMILAR = re.compile(
    r"\b(?:similar to|like)\s+((?:our\s+)?[a-z0-9][\w&'.-]*(?:\s+[a-z0-9][\w&'.-]*){0,3})"
)
NUMBER = re.compile(r"\b(\d{1,3})\b")

STOPWORDS = frozenset(
    (  # noqa: SIM905 - a word list reads better as prose
        "a about all an and any are as at based be been best but by can companies company "
        "business businesses could contact find firm firms for from get give good great has have "
        "having i in is it its likely list located look looks me might more my need needs of on "
        "or organisation organisations organization organizations our please should show strong "
        "than that the their them these they this those to us week weak we what where which who "
        "with within without would year years month months day days last past recent recently "
        "benefit opportunity opportunities lead leads account accounts verkies next top uk new "
        "service services solution solutions ltd limited also just only some very really "
    ).split()
)


@dataclass
class Vocabulary:
    """Words that come from the user's own data, so search speaks the CRM's language."""

    industries: list[str] = field(default_factory=list)
    cities: list[str] = field(default_factory=list)
    # Opportunity category key -> its display name, e.g. "seo" -> "SEO".
    category_names: dict[str, str] = field(default_factory=dict)


@dataclass
class Filters:
    topics: list[str] = field(default_factory=list)  # name, industry or description mentions
    industries: list[str] = field(default_factory=list)
    cities: list[str] = field(default_factory=list)
    country: str | None = None
    categories: list[str] = field(default_factory=list)  # any of these opportunities
    # Each group is one requested signal; an account must show every group (any kind within it).
    signal_groups: list[list[str]] = field(default_factory=list)
    signal_window: timedelta = timedelta(days=365)
    bands: list[str] = field(default_factory=list)
    account_types: list[str] = field(default_factory=list)
    owner: str | None = None  # "me" or "unassigned"
    top_leads: bool = False
    limit: int = 20


@dataclass
class Understood:
    phrase: str
    meaning: str


@dataclass
class Interpretation:
    filters: Filters
    understood: list[Understood]
    unsupported: list[Understood]


def _normalise(query: str) -> str:
    text = query.lower().replace(chr(0x2019), "'")  # a typographic apostrophe
    text = re.sub(r"[^\w&'.\- ]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return f" {text} "


def _singular(word: str) -> str:
    if word.endswith("ies") and len(word) > 4:
        return word[:-3] + "y"
    if word.endswith("s") and not word.endswith(("ss", "as", "us")) and len(word) > 4:
        return word[:-1]
    return word


def interpret(query: str, vocab: Vocabulary) -> Interpretation:
    text = _normalise(query)
    f = Filters()
    understood: list[Understood] = []
    unsupported: list[Understood] = []

    def consume(pattern: str | re.Pattern[str], on_match: Callable[[re.Match[str]], None]) -> None:
        nonlocal text
        regex = (
            pattern
            if isinstance(pattern, re.Pattern)
            else re.compile(rf"(?<![\w]){re.escape(pattern)}(?![\w])")
        )
        while (m := regex.search(text)) is not None:
            on_match(m)
            text = text[: m.start()] + " | " + text[m.end() :]

    def phrases(table: dict[str, Any], handle: Callable[[str, Any], None]) -> None:
        def handler(phrase: str) -> Callable[[re.Match[str]], None]:
            def on_match(m: re.Match[str]) -> None:
                handle(m.group(0).strip(), table[phrase])

            return on_match

        for phrase in sorted(table, key=len, reverse=True):
            consume(phrase, handler(phrase))

    def similar(m: re.Match[str]) -> None:
        unsupported.append(
            Understood(
                m.group(0).strip().rstrip(".'-"),
                "Similarity search is not available yet: client similarity stays Unknown until the "
                "reference-project profiles are complete.",
            )
        )

    consume(SIMILAR, similar)

    def window(m: re.Match[str]) -> None:
        n, unit = int(m.group(1)), m.group(2)
        days = {"day": 1, "week": 7, "month": 30, "year": 365}[unit] * n
        f.signal_window = timedelta(days=max(1, min(days, 5 * 365)))
        understood.append(
            Understood(
                m.group(0).strip(),
                f"Signals dated within the last {n} {unit}{'s' if n != 1 else ''}",
            )
        )

    consume(WINDOW, window)

    def top(m: re.Match[str]) -> None:
        f.top_leads = True
        if m.group(1):
            f.limit = max(1, min(int(m.group(1)), MAX_LIMIT))
        understood.append(
            Understood(m.group(0).strip(), "Best available prospects, ranked by priority")
        )

    consume(TOP_LEADS, top)

    def owner(value: str, meaning: str) -> Callable[[re.Match[str]], None]:
        def handle(m: re.Match[str]) -> None:
            f.owner = value
            understood.append(Understood(m.group(0).strip(), meaning))

        return handle

    consume(
        re.compile(r"\b(?:no owner|unassigned|nobody owns)\b"),
        owner("unassigned", "Accounts with no owner"),
    )
    consume(
        re.compile(r"\b(?:my|mine)\b(?=.*\b(?:accounts?|leads?|prospects?|companies)\b)|\bmine\b"),
        owner("me", "Accounts you own"),
    )

    def country(phrase: str, value: tuple[str, str]) -> None:
        f.country = value[0]
        understood.append(Understood(phrase, f"Based in {value[1]}"))

    phrases(COUNTRIES, country)

    def city(phrase: str, _: object) -> None:
        if phrase not in f.cities:
            f.cities.append(phrase)
        understood.append(Understood(phrase, f"Located in {phrase.title()}"))

    phrases({c: None for c in (*CITIES, *(c.lower() for c in vocab.cities if c))}, city)

    def signal(phrase: str, value: tuple[tuple[str, ...], str]) -> None:
        if list(value[0]) not in f.signal_groups:
            f.signal_groups.append(list(value[0]))
        understood.append(Understood(phrase, f"Buying signal: {value[1]}"))

    phrases(SIGNALS, signal)

    def category(phrase: str, value: tuple[str, ...]) -> None:
        f.categories += [k for k in value if k not in f.categories]
        names = (vocab.category_names.get(k, k.replace("_", " ")) for k in value)
        understood.append(Understood(phrase, "Opportunity detected: " + " or ".join(names)))

    phrases(CATEGORIES, category)

    def band(phrase: str, value: tuple[tuple[str, ...], str]) -> None:
        f.bands += [b for b in value[0] if b not in f.bands]
        understood.append(Understood(phrase, value[1]))

    phrases(BANDS, band)

    def account_type(phrase: str, value: tuple[tuple[str, ...], str]) -> None:
        f.account_types += [t for t in value[0] if t not in f.account_types]
        understood.append(Understood(phrase, f"Account type: {value[1]}"))

    phrases(TYPES, account_type)

    def industry(phrase: str, _: object) -> None:
        f.industries.append(phrase)
        understood.append(Understood(phrase, f"Industry is {phrase}"))

    phrases({i.lower(): None for i in vocab.industries if i and len(i) > 2}, industry)

    def number(m: re.Match[str]) -> None:
        f.limit = max(1, min(int(m.group(1)), MAX_LIMIT))
        understood.append(Understood(m.group(1), f"Show {f.limit}"))

    consume(NUMBER, number)

    for word in re.split(r"[\s|\-]+", text):
        word = word.strip("'.-&")
        if len(word) < 3 or word in STOPWORDS or not re.search(r"[a-z]", word):
            continue
        topic = _singular(word)
        if topic not in f.topics:
            f.topics.append(topic)
            understood.append(Understood(word, f"Name, industry or description mentions “{topic}”"))

    return Interpretation(filters=f, understood=understood, unsupported=unsupported)
