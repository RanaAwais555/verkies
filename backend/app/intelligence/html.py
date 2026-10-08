"""Small HTML helpers shared by the extractors."""

import json
import re
from collections.abc import Iterator
from typing import Any
from urllib.parse import urlsplit

from app.intelligence.types import Page
from app.research.urls import normalise_url, same_site, site_domain


def meta(page: Page, name: str) -> str | None:
    """<meta name=...> or <meta property=...> content, stripped, or None."""
    wanted = name.lower()
    for node in page.tree.css("meta[content]"):
        attrs = node.attributes
        if (attrs.get("name") or attrs.get("property") or "").lower() == wanted:
            value = (attrs.get("content") or "").strip()
            if value:
                return value
    return None


def links(page: Page) -> Iterator[tuple[str, str, Any]]:
    """(absolute URL, link text, node) for every <a href>."""
    for node in page.tree.css("a[href]"):
        href = (node.attributes.get("href") or "").strip()
        url = normalise_url(href, page.url) if not href.startswith(("mailto:", "tel:")) else href
        if url:
            yield url, " ".join((node.text() or "").split()), node


def script_sources(page: Page) -> list[str]:
    return [n.attributes.get("src") or "" for n in page.tree.css("script[src]")]


def json_ld(page: Page) -> list[dict[str, Any]]:
    """Every JSON-LD object on the page, @graph flattened. Malformed blocks are skipped."""
    found: list[dict[str, Any]] = []

    def walk(item: Any) -> None:
        if isinstance(item, list):
            for entry in item:
                walk(entry)
        elif isinstance(item, dict):
            found.append(item)
            if "@graph" in item:
                walk(item["@graph"])

    for node in page.tree.css('script[type="application/ld+json"]'):
        try:
            walk(json.loads(node.text() or ""))
        except (ValueError, RecursionError):
            continue
    return found


def ld_types(item: dict[str, Any]) -> list[str]:
    value = item.get("@type")
    if isinstance(value, list):
        return [str(v) for v in value]
    return [str(value)] if value else []


def is_internal(url: str, home_url: str) -> bool:
    return same_site(url, site_domain(urlsplit(home_url).hostname or ""))


def first_match(pattern: re.Pattern[str], text: str) -> re.Match[str] | None:
    return pattern.search(text)
