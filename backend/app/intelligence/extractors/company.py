"""Who the company is, from its own pages: name, description, location hints, social profiles,
founding year and named people. Only what the site states; nothing is guessed."""

import re
from typing import Any
from urllib.parse import urlsplit

from app.core.enums import EvidenceType
from app.intelligence.html import json_ld, ld_types, links, meta
from app.intelligence.types import Area, Observation, Page, SiteContext, excerpt

ORG_TYPES = {
    "Organization",
    "Corporation",
    "LocalBusiness",
    "ProfessionalService",
    "LegalService",
    "Attorney",
    "Store",
    "OnlineBusiness",
    "EducationalOrganization",
    "MedicalOrganization",
}
SOCIAL = {
    "linkedin.com/company/": "linkedin",
    "twitter.com/": "x",
    "x.com/": "x",
    "facebook.com/": "facebook",
    "instagram.com/": "instagram",
    "youtube.com/": "youtube",
    "github.com/": "github",
    "tiktok.com/@": "tiktok",
}
FOUNDED = re.compile(r"\b(?:founded|established|est\.|since)\s+(?:in\s+)?((?:19|20)\d{2})\b", re.I)
ROLE = re.compile(
    r"\b(co-?founder|founder|chief [a-z]+ officer|ceo|cto|coo|cfo|cmo|cpo|managing director|"
    r"managing partner|director(?: of [a-z ]+)?|head of [a-z ]+|vp(?: of)? [a-z ]+|vice president|"
    r"partner|principal|president|owner|lead [a-z]+|[a-z]+ lead|[a-z]+ manager|solicitor|"
    r"immigration adviser|consultant)\b",
    re.I,
)
NAME = re.compile(r"^[A-Z][a-zA-Z'’.-]+(?: [A-Z][a-zA-Z'’.-]+){1,3}$")  # noqa: RUF001 - curly apostrophes occur in names
NOT_NAMES = re.compile(
    r"\b(Our|Team|About|Contact|Services|Meet|The|Get|Book|Read|Learn|View|"
    r"Privacy|Terms|Home|Blog|News|Careers|Pricing)\b"
)
PHONE_COUNTRY = {
    "+44": "GB",
    "+1": "US/CA",
    "+61": "AU",
    "+353": "IE",
    "+971": "AE",
    "+31": "NL",
    "+49": "DE",
    "+33": "FR",
    "+41": "CH",
    "+46": "SE",
    "+45": "DK",
    "+92": "PK",
    "+91": "IN",
}
TLD_COUNTRY = {
    "uk": "GB",
    "au": "AU",
    "ca": "CA",
    "ie": "IE",
    "ae": "AE",
    "nl": "NL",
    "de": "DE",
    "fr": "FR",
    "ch": "CH",
    "se": "SE",
    "dk": "DK",
    "pk": "PK",
    "in": "IN",
}


def extract(pages: list[Page], ctx: SiteContext) -> list[Observation]:
    home = next((p for p in pages if p.category == "home"), pages[0])
    out: list[Observation] = []

    def obs(key: str, value: object, page: Page, text: str, **kw: object) -> None:
        out.append(Observation(Area.COMPANY, f"company.{key}", value, page.url, text, **kw))  # type: ignore[arg-type]

    orgs = [(p, item) for p in pages for item in json_ld(p) if ORG_TYPES & set(ld_types(item))]
    site_name = meta(home, "og:site_name")
    if site_name:
        obs(
            "name",
            site_name,
            home,
            f'<meta property="og:site_name" content="{site_name}">',
            confidence=0.85,
        )
    elif orgs and isinstance(orgs[0][1].get("name"), str):
        page, org = orgs[0]
        obs(
            "name",
            org["name"],
            page,
            f"JSON-LD {ld_types(org)[0]} name: {org['name']}",
            evidence_type=EvidenceType.STRUCTURED_DATA,
            confidence=0.85,
        )
    else:
        title_node = home.tree.css_first("title")
        title = " ".join((title_node.text() if title_node else "").split())
        if title:
            name = re.split(r"\s+[|–—-]\s+", title)[0].strip()  # noqa: RUF001 - dashes used as separators
            obs("name", name, home, f"<title>{title}</title>", confidence=0.5)

    description = meta(home, "description") or meta(home, "og:description")
    if description:
        obs("description", description, home, description[:300], confidence=0.8)

    for page, org in orgs:
        address = org.get("address")
        if isinstance(address, list):
            address = address[0] if address else None
        if isinstance(address, dict):
            fields = {
                k: address.get(k)
                for k in (
                    "streetAddress",
                    "addressLocality",
                    "addressRegion",
                    "postalCode",
                    "addressCountry",
                )
            }
            country = fields.get("addressCountry")
            if isinstance(country, dict):
                fields["addressCountry"] = country.get("name") or country.get("@id")
            cleaned = {k: v for k, v in fields.items() if isinstance(v, str) and v.strip()}
            if cleaned:
                obs(
                    "address",
                    cleaned,
                    page,
                    f"JSON-LD address: {', '.join(cleaned.values())}",
                    evidence_type=EvidenceType.STRUCTURED_DATA,
                    confidence=0.9,
                )
                break

    hints = _country_hints(pages, home)
    for value, page, text, confidence in hints:
        obs("country_hint", value, page, text, confidence=confidence)

    profiles: dict[str, str] = {}
    profile_page: Page | None = None
    for page in pages:
        for url, _, _ in links(page):
            low = url.lower()
            for marker, network in SOCIAL.items():
                if marker in low and network not in profiles and _profile_path(url):
                    profiles[network] = url
                    profile_page = profile_page or page
    if profiles and profile_page is not None:
        obs(
            "social_profiles",
            profiles,
            profile_page,
            "; ".join(f"{k}: {v}" for k, v in list(profiles.items())[:5]),
            confidence=0.9,
        )
    if "linkedin" in profiles and profile_page is not None:
        obs(
            "linkedin_company_url",
            profiles["linkedin"],
            profile_page,
            f"LinkedIn link: {profiles['linkedin']}",
            confidence=0.9,
        )

    founded = next(((p, m) for p in pages if (m := FOUNDED.search(p.text))), None)
    if founded:
        page, match = founded
        obs(
            "founded_year",
            int(match.group(1)),
            page,
            excerpt(page.text, match.group(0), 160),
            confidence=0.75,
        )

    for person, page, text, kind, confidence in _people(pages):
        obs("person", person, page, text, evidence_type=kind, confidence=confidence)
    return out


def _profile_path(url: str) -> bool:
    path = urlsplit(url).path.strip("/")
    return bool(path) and not path.startswith(("share", "sharer", "intent", "home"))


def _country_hints(pages: list[Page], home: Page) -> list[tuple[str, Page, str, float]]:
    hints: list[tuple[str, Page, str, float]] = []
    host = urlsplit(home.url).hostname or ""
    tld = host.rsplit(".", 1)[-1]
    if tld in TLD_COUNTRY:
        hints.append((TLD_COUNTRY[tld], home, f"Domain ends in .{tld} ({host})", 0.6))
    for page in pages:
        for url, _, _ in links(page):
            if url.lower().startswith("tel:"):
                number = url[4:].replace(" ", "").replace("-", "")
                for prefix, country in sorted(PHONE_COUNTRY.items(), key=lambda kv: -len(kv[0])):
                    if number.startswith(prefix):
                        hints.append((country, page, f"Phone number {url[4:]}", 0.7))
                        break
                else:
                    continue
                return hints
    return hints


def _people(pages: list[Page]) -> list[tuple[dict[str, str], Page, str, EvidenceType, float]]:
    """Named people with a role, from JSON-LD Person data or name/role pairs on team pages."""
    found: list[tuple[dict[str, str], Page, str, EvidenceType, float]] = []
    seen: set[str] = set()
    for page in pages:
        for item in json_ld(page):
            if "Person" in ld_types(item) and isinstance(item.get("name"), str):
                name = item["name"].strip()
                title = item.get("jobTitle") if isinstance(item.get("jobTitle"), str) else None
                if name and name not in seen:
                    seen.add(name)
                    person = {"name": name, **({"title": title} if title else {})}
                    found.append(
                        (
                            person,
                            page,
                            f"JSON-LD Person: {name}" + (f", {title}" if title else ""),
                            EvidenceType.STRUCTURED_DATA,
                            0.85,
                        )
                    )
    for page in pages:
        if page.category not in ("team", "about", "home"):
            continue
        for node in page.tree.css("h2, h3, h4, h5, h6, strong, b"):
            name = " ".join((node.text() or "").split())
            if not NAME.match(name) or NOT_NAMES.search(name) or name in seen:
                continue
            role = _role_after(node)
            if role:
                seen.add(name)
                found.append(
                    (
                        {"name": name, "title": role},
                        page,
                        f"{name} — {role}",
                        EvidenceType.PAGE_CONTENT,
                        0.6,
                    )
                )
    return found[:25]


def _role_after(node: Any) -> str | None:
    """The role text right after a name heading (next element, or the rest of its parent)."""
    candidates: list[str] = []
    sibling = node.next
    for _ in range(3):
        if sibling is None:
            break
        text = " ".join((sibling.text() or "").split())
        if text:
            candidates.append(text)
            break
        sibling = sibling.next
    parent = node.parent
    if parent is not None:
        candidates.append(" ".join((parent.text() or "").split()))
    for text in candidates:
        match = ROLE.search(text[:120])
        if match:
            start = text.find(match.group(0))
            return text[start : start + 60].split(" | ")[0].split(".")[0].strip()
    return None
