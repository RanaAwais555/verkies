"""Fetch budgets, results and errors (PROVIDER_SPEC.md §4)."""

from dataclasses import dataclass, field

from app.providers.errors import ProviderError

HTML_TYPES = frozenset({"text/html", "application/xhtml+xml"})
DEFAULT_CONTENT_TYPES = HTML_TYPES | frozenset(
    {"text/plain", "application/xml", "text/xml", "application/json"}
)


@dataclass(frozen=True)
class FetchBudget:
    max_bytes: int = 2 * 1024 * 1024  # per response, after decompression
    max_redirects: int = 5
    timeout_seconds: float = 15.0
    allowed_ports: frozenset[int] = frozenset({80, 443})
    content_types: frozenset[str] = DEFAULT_CONTENT_TYPES


@dataclass(frozen=True)
class FetchResult:
    url: str  # as requested
    final_url: str  # after redirects
    status: int
    headers: dict[str, str]
    content_type: str | None  # media type only, lower case, no parameters
    body: bytes
    redirects: list[str] = field(default_factory=list)
    elapsed_ms: int = 0

    @property
    def is_html(self) -> bool:
        return self.content_type in HTML_TYPES

    def text(self) -> str:
        return self.body.decode(_charset(self.headers.get("content-type")), errors="replace")


def _charset(content_type: str | None) -> str:
    for part in (content_type or "").split(";")[1:]:
        key, _, value = part.strip().partition("=")
        if key.lower() == "charset" and value:
            try:
                "".encode(value.strip('"'))
            except LookupError:
                break
            return value.strip('"')
    return "utf-8"


class FetchBlocked(ProviderError):
    """Refused by policy before or during the request: never retried around (SECURITY.md §3)."""

    code = "fetch_blocked"


class FetchFailed(ProviderError):
    """Network-level failure: DNS, connection, TLS, timeout."""

    code = "fetch_failed"
