"""Website changes on a watched account (master context §15 Monitoring; slice 6.2).

The pages an account's latest research read are read again and compared with the last copy VROS
kept of each (the cached response, which every later read replaces). What is compared:

- pages: a page now linked from the homepage that was not before, a link that was dropped, a
  page that now answers 404 or 410, and a page whose visible text differs;
- facts: services, pricing, technology and contact routes, by running the same extractors over
  the old and the new copies of the same pages, so a page that could not be read again changes
  nothing.

A change is only reported when the content differs, and each carries the text before and after.
A page that could not be fetched is an error, never a removal.
"""

import difflib
import uuid
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import PageKind
from app.intelligence.runner import analyse
from app.intelligence.types import Observation, Page, SiteContext
from app.providers.errors import ProviderError
from app.providers.storage import Storage
from app.research.crawler import ASSET_SUFFIXES, PageSource, categorise, extract_links
from app.research.models import RawResponse, ResearchPage
from app.research.urls import same_site, site_domain

GONE = frozenset({404, 410})
CONTEXT_WORDS = 12
MAX_EXCERPT = 300

CATEGORY_LABELS = {
    "home": "Homepage",
    "about": "About page",
    "team": "Team page",
    "services": "Services page",
    "product": "Product page",
    "pricing": "Pricing page",
    "contact": "Contact page",
    "careers": "Careers page",
}
# Homepage links that come and go with every post: news is watched through its feeds (6.1).
CHURNING = frozenset({"blog"})
# Pages whose changes are about what the account sells.
TOPIC_OF_CATEGORY = {"services": "services", "product": "services", "pricing": "pricing"}


@dataclass(frozen=True)
class Tracked:
    topic: str  # services, pricing, technology, contact
    label: str
    presence: bool = False  # only whether it is there counts, not its wording


TRACKED: dict[str, Tracked] = {
    "technology.detected": Tracked("technology", "Technology"),
    "technology.generator": Tracked("technology", "Site built with"),
    "conversion.contact_form": Tracked("contact", "Contact form"),
    "conversion.email_addresses": Tracked("contact", "Email address"),
    "conversion.phone_numbers": Tracked("contact", "Phone number"),
    "conversion.whatsapp": Tracked("contact", "WhatsApp"),
    "conversion.booking_tool": Tracked("contact", "Online booking"),
    "conversion.live_chat": Tracked("contact", "Live chat"),
    "conversion.pricing_page": Tracked("pricing", "Pricing page", presence=True),
    "product.subscription_pricing": Tracked("pricing", "Subscription pricing", presence=True),
    "product.payments": Tracked("pricing", "Online payments"),
}


@dataclass(frozen=True)
class Snapshot:
    """The last copy VROS kept of a page."""

    url: str
    category: str | None
    html: str
    fetched_at: datetime


@dataclass
class Change:
    change: str  # page_added, page_removed, page_changed, added, removed
    topic: str  # services, pricing, technology, contact, pages
    title: str
    url: str
    after: str
    before: str | None = None
    before_url: str | None = None
    before_seen_at: datetime | None = None

    def detail(self) -> dict[str, Any]:
        return {
            "change": self.change,
            "topic": self.topic,
            "before": self.before,
            "before_url": self.before_url,
            "before_seen_at": self.before_seen_at.isoformat() if self.before_seen_at else None,
            "after": self.after,
        }


@dataclass
class Reread:
    """What reading the pages again produced."""

    pages: list[tuple[Snapshot, Page]] = field(default_factory=list)  # read again, both copies
    gone: list[tuple[Snapshot, int]] = field(default_factory=list)  # now 404 or 410
    errors: list[str] = field(default_factory=list)


# --- loading and reading ---------------------------------------------------------------------


async def snapshots(
    db: AsyncSession, research_run_id: uuid.UUID, storage: Storage
) -> list[Snapshot]:
    """The pages the research read, each with the latest plain (not rendered) copy kept.
    Research may have rendered a page; the check reads plain HTML, so it compares plain HTML."""
    pages = (
        await db.execute(
            select(ResearchPage)
            .where(
                ResearchPage.research_run_id == research_run_id,
                ResearchPage.kind == PageKind.PAGE,
                ResearchPage.skip_reason.is_(None),
                ResearchPage.duplicate_of_url.is_(None),
                ResearchPage.raw_response_id.is_not(None),
            )
            .order_by(ResearchPage.created_at, ResearchPage.id)
        )
    ).scalars()
    out: list[Snapshot] = []
    seen: set[str] = set()
    for page in pages:
        if page.url in seen:
            continue
        seen.add(page.url)
        raw = (
            await db.execute(
                select(RawResponse)
                .where(
                    RawResponse.url == page.url,
                    RawResponse.rendered.is_(False),
                    RawResponse.status_code == 200,
                    RawResponse.body_ref.is_not(None),
                )
                .order_by(RawResponse.fetched_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if raw is None or raw.body_ref is None:
            continue
        try:
            body = storage.get(raw.body_ref)
        except (OSError, ValueError):
            continue  # the stored copy is lost: nothing to compare with
        html = body.decode("utf-8", errors="replace")
        out.append(Snapshot(page.url, page.category, html, raw.fetched_at))
    return out


async def reread(source: PageSource, old: list[Snapshot]) -> Reread:
    result = Reread()
    for snap in old:
        try:
            fetched = await source.fetch(snap.url)
        except ProviderError as exc:
            result.errors.append(f"{snap.url}: {exc}")
            continue
        status = fetched.result.status
        if status in GONE:
            result.gone.append((snap, status))
        elif status != 200 or not (fetched.result.content_type or "").startswith("text/html"):
            result.errors.append(f"{snap.url}: answered {status}")
        else:
            html = fetched.result.body.decode("utf-8", errors="replace")
            result.pages.append(
                (snap, Page(url=snap.url, html=html, category=snap.category, headers={}))
            )
    return result


# --- comparing ---------------------------------------------------------------------------------


def _text(html: str, url: str, category: str | None) -> str:
    return Page(url=url, html=html, category=category).text


def _clip(words: list[str]) -> str:
    text = " ".join(words)
    return text if len(text) <= MAX_EXCERPT else text[: MAX_EXCERPT - 1].rstrip() + "…"


def text_change(before: str, after: str) -> tuple[str, str, int] | None:
    """(before excerpt, after excerpt, number of changed passages), or None if the same."""
    a, b = before.split(), after.split()
    if a == b:
        return None
    # Edits a few words apart are one passage: [i1, i2, j1, j2] per passage.
    passages: list[list[int]] = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag == "equal":
            continue
        if passages and i1 - passages[-1][1] <= CONTEXT_WORDS:
            passages[-1][1], passages[-1][3] = i2, j2
        else:
            passages.append([i1, i2, j1, j2])
    i1, i2, j1, j2 = passages[0]
    old = a[max(0, i1 - CONTEXT_WORDS) : i2 + CONTEXT_WORDS]
    new = b[max(0, j1 - CONTEXT_WORDS) : j2 + CONTEXT_WORDS]
    return _clip(old), _clip(new), len(passages)


def _label(snap: Snapshot) -> str:
    return CATEGORY_LABELS.get(snap.category or "", f"Page {urlsplit(snap.url).path or '/'}")


def home_links(html: str, url: str) -> dict[str, str]:
    """The site's own pages the homepage links to, by URL, with their link text: the kinds of
    page research reads (services, pricing, contact...), not posts."""
    out: dict[str, str] = {}
    site = site_domain(urlsplit(url).hostname or "")
    for link, text in extract_links(html, url):
        path = urlsplit(link).path.lower()
        if (
            same_site(link, site)
            and link.rstrip("/") != url.rstrip("/")
            and not path.endswith(ASSET_SUFFIXES)
            and categorise(link, text) not in (None, *CHURNING)
        ):
            out.setdefault(link, text)
    return out


def _items(key: str, value: Any) -> set[str]:
    tracked = TRACKED[key]
    if value is None or value is False or value == [] or value == "":
        return set()
    if tracked.presence or value is True:
        return {tracked.label}
    if isinstance(value, dict):
        return {str(value.get("name") or value)}
    if isinstance(value, list):
        return {str(v) for v in value}
    return {str(value)}


def facts(observations: Iterable[Observation]) -> dict[tuple[str, str], Observation]:
    """Each tracked item seen, by (key, item), with the observation that showed it."""
    out: dict[tuple[str, str], Observation] = {}
    for o in observations:
        if o.key in TRACKED:
            for item in _items(o.key, o.value):
                out.setdefault((o.key, item), o)
    return out


def _fact_title(key: str, item: str, added: bool) -> str:
    tracked = TRACKED[key]
    if item == tracked.label:
        return f"{tracked.label} {'added' if added else 'removed'}"
    return f"{tracked.label} {'added' if added else 'removed'}: {item}"


def compare(read: Reread) -> list[Change]:
    changes: list[Change] = []
    for snap, status in read.gone:
        changes.append(
            Change(
                "page_removed",
                TOPIC_OF_CATEGORY.get(snap.category or "", "pages"),
                f"{_label(snap)} removed (now answers {status})",
                snap.url,
                after=f"{snap.url} answered {status}",
                before=_clip(_text(snap.html, snap.url, snap.category).split()),
                before_url=snap.url,
                before_seen_at=snap.fetched_at,
            )
        )
    home = next(((s, p) for s, p in read.pages if s.category == "home"), None)
    if home is not None:
        snap, page = home
        old_links, new_links = home_links(snap.html, snap.url), home_links(page.html, page.url)
        known = {s.url for s, _ in read.pages} | {s.url for s, _ in read.gone}
        for link, text in new_links.items():
            if link not in old_links and link not in known:
                category = categorise(link, text)
                changes.append(
                    Change(
                        "page_added",
                        TOPIC_OF_CATEGORY.get(category or "", "pages"),
                        f"New page linked from the homepage: {text or urlsplit(link).path}",
                        link,
                        after=f'Homepage link "{text}" → {link}',
                        before_url=snap.url,
                        before_seen_at=snap.fetched_at,
                    )
                )
        gone = {s.url for s, _ in read.gone}
        for link, text in old_links.items():
            if link not in new_links and link not in gone:
                category = categorise(link, text)
                changes.append(
                    Change(
                        "page_removed",
                        TOPIC_OF_CATEGORY.get(category or "", "pages"),
                        f"No longer linked from the homepage: {text or urlsplit(link).path}",
                        link,
                        after=f"The homepage no longer links to {link}",
                        before=f'Homepage link "{text}" → {link}',
                        before_url=snap.url,
                        before_seen_at=snap.fetched_at,
                    )
                )
    for snap, page in read.pages:
        diff = text_change(_text(snap.html, snap.url, snap.category), page.text)
        if diff is not None:
            before, after, passages = diff
            more = f" ({passages} passages)" if passages > 1 else ""
            changes.append(
                Change(
                    "page_changed",
                    TOPIC_OF_CATEGORY.get(snap.category or "", "pages"),
                    f"{_label(snap)} changed{more}",
                    snap.url,
                    after=after,
                    before=before,
                    before_url=snap.url,
                    before_seen_at=snap.fetched_at,
                )
            )
    if read.pages:
        changes += _fact_changes(read)
    return changes


def _fact_changes(read: Reread) -> list[Change]:
    ctx = SiteContext(home_url=read.pages[0][0].url, robots="missing")
    old_pages = [
        Page(url=s.url, html=s.html, category=s.category, headers={}) for s, _ in read.pages
    ]
    old, _ = analyse(old_pages, ctx)
    new, _ = analyse([p for _, p in read.pages], ctx)
    before, after = facts(old), facts(new)
    seen_at = {s.url: s.fetched_at for s, _ in read.pages}
    checked = len(read.pages)
    same = f"the same {checked} page{'s' if checked != 1 else ''}"
    changes: list[Change] = []
    for (key, item), o in after.items():
        if (key, item) not in before:
            changes.append(
                Change(
                    "added",
                    TRACKED[key].topic,
                    _fact_title(key, item, True),
                    o.source_url,
                    after=o.excerpt,
                    before=f"Not found on {same}",
                    before_seen_at=min(seen_at.values()),
                )
            )
    for (key, item), o in before.items():
        if (key, item) not in after:
            changes.append(
                Change(
                    "removed",
                    TRACKED[key].topic,
                    _fact_title(key, item, False),
                    o.source_url,
                    after=f"No longer found on {same}",
                    before=o.excerpt,
                    before_url=o.source_url,
                    before_seen_at=seen_at.get(o.source_url),
                )
            )
    return changes
