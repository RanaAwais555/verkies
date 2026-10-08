"""URL normalisation and same-site checks for crawling."""

from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

from app.core.errors import ValidationFailed

TRACKING_PARAMS = frozenset({"gclid", "fbclid", "msclkid", "mc_cid", "mc_eid", "_ga", "ref"})
DEFAULT_PORTS = {"http": 80, "https": 443}


def normalise_url(url: str, base: str | None = None) -> str | None:
    """Absolute, lower-case scheme/host, no default port, fragment or tracking parameters.
    Returns None for anything that is not an http(s) URL."""
    try:
        parts = urlsplit(urljoin(base, url.strip()) if base else url.strip())
        port = parts.port
    except ValueError:
        return None
    scheme = parts.scheme.lower()
    if scheme not in DEFAULT_PORTS or not parts.hostname:
        return None
    host = parts.hostname.lower().rstrip(".")
    netloc = host if port in (None, DEFAULT_PORTS[scheme]) else f"{host}:{port}"
    query = urlencode(
        [
            (k, v)
            for k, v in parse_qsl(parts.query, keep_blank_values=True)
            if not k.lower().startswith("utm_") and k.lower() not in TRACKING_PARAMS
        ]
    )
    return urlunsplit((scheme, netloc, parts.path or "/", query, ""))


def site_domain(host: str) -> str:
    host = host.lower().rstrip(".")
    return host[4:] if host.startswith("www.") else host


def normalised_domain(user_input: str) -> tuple[str, str]:
    """From what a person typed ("acme.com", "https://www.acme.com/x") to (start URL, domain)."""
    raw = user_input.strip()
    if not raw:
        raise ValidationFailed("Enter a company website.")
    if "://" not in raw:
        raw = f"https://{raw}"
    try:
        parts = urlsplit(raw)
    except ValueError as exc:
        raise ValidationFailed("That website address is not valid.") from exc
    if parts.username is not None or parts.password is not None:
        raise ValidationFailed("Remove the username and password from the address.")
    url = normalise_url(raw)
    if url is None:
        raise ValidationFailed("Enter a website address starting with http:// or https://.")
    host = urlsplit(url).hostname or ""
    if "." not in host.strip("[]"):
        raise ValidationFailed("Enter a full domain name, such as acme.com.")
    try:
        domain = site_domain(host).encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise ValidationFailed("That domain name is not valid.") from exc
    return url, domain


def same_site(url: str, domain: str) -> bool:
    host = urlsplit(url).hostname or ""
    site = site_domain(host)
    return site == domain or site.endswith(f".{domain}")
