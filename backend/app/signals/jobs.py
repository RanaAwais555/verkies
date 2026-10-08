"""Public job-board APIs (PROVIDER_SPEC.md §3: keyless JSON published by the boards for this
purpose). A board is only queried when the company's own site links to it."""

import re
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any
from urllib.parse import quote

TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,99}$")

# Where each board publishes its open roles. Tests point these at a local server.
DEFAULT_API = {
    "greenhouse": "https://boards-api.greenhouse.io/v1/boards/{token}/jobs",
    "lever": "https://api.lever.co/v0/postings/{token}?mode=json",
    "ashby": "https://api.ashbyhq.com/posting-api/job-board/{token}",
    "workable": "https://apply.workable.com/api/v1/widget/accounts/{token}",
}
PROVIDER_NAMES = {
    "greenhouse": "Greenhouse",
    "lever": "Lever",
    "ashby": "Ashby",
    "workable": "Workable",
}


@dataclass(frozen=True)
class JobPosting:
    provider: str
    title: str
    url: str | None
    location: str | None
    department: str | None
    published: date | None


@dataclass(frozen=True)
class JobBoards:
    api: dict[str, str]

    @classmethod
    def default(cls) -> "JobBoards":
        return cls(dict(DEFAULT_API))

    def url(self, provider: str, token: str) -> str | None:
        """The API URL, or None for boards without a public API or a malformed token."""
        template = self.api.get(provider)
        if template is None or not TOKEN.match(token):
            return None
        return template.format(token=quote(token, safe=""))


def _date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    try:
        if isinstance(value, int | float):  # Lever: milliseconds since the epoch
            return datetime.fromtimestamp(value / 1000, tz=UTC).date()
        text = str(value).strip()
        if len(text) == 10:
            return date.fromisoformat(text)
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except (ValueError, OverflowError, OSError):
        return None


def _text(value: Any, limit: int = 200) -> str | None:
    if isinstance(value, dict):
        value = value.get("name") or value.get("location")
    if not isinstance(value, str):
        return None
    return " ".join(value.split())[:limit] or None


def parse(provider: str, data: Any) -> list[JobPosting]:
    """Postings from a board's JSON. Anything unexpected is skipped, never guessed."""
    if provider == "lever":
        items = data if isinstance(data, list) else []
    elif isinstance(data, dict):
        items = data.get("jobs") or []
    else:
        items = []
    out: list[JobPosting] = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        if provider == "greenhouse":
            title, url = item.get("title"), item.get("absolute_url")
            location, dept = item.get("location"), (item.get("departments") or [{}])[0]
            published = item.get("first_published") or item.get("updated_at")
        elif provider == "lever":
            title, url = item.get("text"), item.get("hostedUrl")
            cats = item.get("categories") or {}
            location, dept = cats.get("location"), cats.get("team")
            published = item.get("createdAt")
        elif provider == "ashby":
            title, url = item.get("title"), item.get("jobUrl")
            location, dept = item.get("location"), item.get("department")
            published = item.get("publishedAt")
        elif provider == "workable":
            title, url = item.get("title"), item.get("url") or item.get("shortlink")
            location = ", ".join(p for p in (item.get("city"), item.get("country")) if p) or None
            dept = item.get("department")
            published = item.get("published_on") or item.get("created_at")
        else:
            continue
        clean = _text(title)
        if not clean:
            continue
        link = url if isinstance(url, str) and url.startswith(("https://", "http://")) else None
        out.append(
            JobPosting(provider, clean, link, _text(location), _text(dept, 120), _date(published))
        )
    return out
