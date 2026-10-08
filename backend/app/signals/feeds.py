"""RSS 2.0 and Atom feeds. Documents with a DOCTYPE or entities are refused outright, so
entity expansion and external entities never come into play."""

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date, datetime
from email.utils import parsedate_to_datetime

from app.providers.errors import ProviderError

ATOM = "{http://www.w3.org/2005/Atom}"
MAX_ITEMS = 50


@dataclass(frozen=True)
class FeedItem:
    title: str
    url: str | None
    published: date | None


def _date(text: str | None) -> date | None:
    if not text:
        return None
    text = text.strip()
    try:
        return parsedate_to_datetime(text).date()
    except (TypeError, ValueError, IndexError):
        pass
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _clean(text: str | None) -> str:
    return " ".join((text or "").split())[:300]


def parse(xml: str) -> list[FeedItem]:
    head = xml[:4096].upper()
    if "<!DOCTYPE" in head or "<!ENTITY" in xml.upper():
        raise ProviderError("Feed declares a DOCTYPE or entities; refused.", code="feed_refused")
    try:
        root = ET.fromstring(xml)  # noqa: S314 - DOCTYPE/entities refused above
    except ET.ParseError as exc:
        raise ProviderError("Feed is not valid XML.", code="feed_invalid") from exc
    items: list[FeedItem] = []
    if root.tag == f"{ATOM}feed":
        for entry in root.findall(f"{ATOM}entry")[:MAX_ITEMS]:
            link = next(
                (
                    el.get("href")
                    for el in entry.findall(f"{ATOM}link")
                    if el.get("rel", "alternate") == "alternate"
                ),
                None,
            )
            published = entry.findtext(f"{ATOM}published") or entry.findtext(f"{ATOM}updated")
            title = _clean(entry.findtext(f"{ATOM}title"))
            if title:
                items.append(FeedItem(title, link, _date(published)))
    else:
        for item in root.iter("item"):
            title = _clean(item.findtext("title"))
            if title:
                items.append(
                    FeedItem(
                        title,
                        (item.findtext("link") or "").strip() or None,
                        _date(item.findtext("pubDate")),
                    )
                )
            if len(items) >= MAX_ITEMS:
                break
    return items
