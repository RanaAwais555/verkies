"""Inputs and outputs of the extractors (master context §8).

An extractor is a pure function: crawled pages in, observations out. Each observation names
one fact about the site (a key and a JSON value) and carries the evidence for it: the page it
was seen on, a short excerpt, the kind of evidence and a confidence. Nothing is inferred
beyond what the page shows; "absent" observations say which pages were checked.
"""

from dataclasses import dataclass, field
from datetime import datetime
from functools import cached_property
from typing import Any

from selectolax.lexbor import LexborHTMLParser

from app.core.enums import EvidenceType, ObservationArea

EXCERPT_CHARS = 300


Area = ObservationArea


@dataclass(frozen=True)
class Page:
    url: str  # as fetched (final URL after redirects)
    html: str
    category: str | None  # home, about, team, contact, pricing, careers, ...
    headers: dict[str, str] = field(default_factory=dict)
    bytes: int = 0
    rendered: bool = False

    @cached_property
    def tree(self) -> LexborHTMLParser:
        return LexborHTMLParser(self.html)

    @cached_property
    def text(self) -> str:
        """Visible text, whitespace-collapsed (scripts and styles removed)."""
        tree = LexborHTMLParser(self.html)
        for node in tree.css("script, style, noscript, template, svg"):
            node.decompose()
        body = tree.body
        return " ".join((body.text(separator=" ") if body else "").split())


@dataclass(frozen=True)
class SiteContext:
    home_url: str
    robots: str  # parsed, missing, unreachable
    sitemaps: tuple[str, ...] = ()
    # Every page the crawl asked for, with its HTTP status (None if it was not fetched).
    statuses: dict[str, int | None] = field(default_factory=dict)


@dataclass
class Observation:
    area: Area
    key: str  # dotted, e.g. "conversion.contact_form"
    value: Any  # JSON-serialisable
    source_url: str
    excerpt: str
    evidence_type: EvidenceType = EvidenceType.PAGE_CONTENT
    confidence: float = 0.9
    seen_on: list[str] = field(default_factory=list)
    # When the source says the thing happened (a posting or article date), if it says.
    published_at: datetime | None = None

    def identity(self) -> tuple[str, str]:
        import json

        return self.key, json.dumps(self.value, sort_keys=True, default=str)


def excerpt(text: str, needle: str | None = None, width: int = EXCERPT_CHARS) -> str:
    """A short window of text around needle (or the start of text)."""
    text = " ".join(text.split())
    if not needle:
        return text[:width]
    at = text.lower().find(needle.lower())
    if at < 0:
        return text[:width]
    start = max(0, at - width // 3)
    return ("…" if start else "") + text[start : start + width].strip()


def outer(node: Any, width: int = EXCERPT_CHARS) -> str:
    html = node.html or ""
    return " ".join(html.split())[:width]
