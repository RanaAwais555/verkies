"""Hiring signals from the company's own site (master context §9 buying signals)."""

import re
from urllib.parse import urlsplit

from app.intelligence.html import links
from app.intelligence.types import Area, Observation, Page, SiteContext, excerpt

JOB_BOARDS = (
    ("boards.greenhouse.io/", "greenhouse"),
    ("job-boards.greenhouse.io/", "greenhouse"),
    ("jobs.lever.co/", "lever"),
    ("jobs.ashbyhq.com/", "ashby"),
    ("apply.workable.com/", "workable"),
    (".teamtailor.com", "teamtailor"),
    (".bamboohr.com/careers", "bamboohr"),
    (".recruitee.com", "recruitee"),
    (".myworkdayjobs.com", "workday"),
    (".jobs.personio.", "personio"),
)
TECH_ROLE = re.compile(
    r"\b((?:senior |junior |lead |staff |principal )?"
    r"(?:software|backend|back-end|frontend|front-end|"
    r"full[- ]?stack|mobile|ios|android|devops|platform|data|machine learning|ml|qa|test)"
    r" (?:engineer|developer)|(?:web|software|app) developer|cto|chief technology officer|"
    r"head of (?:engineering|product|technology)|vp (?:of )?engineering|engineering manager|"
    r"product manager|product owner|product designer|ux(?:/ui)? designer|data scientist)\b",
    re.I,
)


def extract(pages: list[Page], ctx: SiteContext) -> list[Observation]:
    out: list[Observation] = []
    careers = [p for p in pages if p.category == "careers"]
    if careers:
        out.append(
            Observation(
                Area.HIRING,
                "hiring.careers_page",
                True,
                careers[0].url,
                f"Careers page: {careers[0].url}",
                confidence=0.9,
            )
        )

    for page in pages:
        for url, text, _ in links(page):
            low = url.lower()
            for marker, provider in JOB_BOARDS:
                if marker in low:
                    parts = urlsplit(url)
                    token = (
                        parts.path.strip("/").split("/")[0]
                        if parts.path.strip("/")
                        else ((parts.hostname or "").split(".")[0])
                    )
                    out.append(
                        Observation(
                            Area.HIRING,
                            "hiring.job_board",
                            {"provider": provider, "token": token, "url": url},
                            page.url,
                            f'Link "{text or url}" → {url}',
                            confidence=0.9,
                        )
                    )
                    break
            else:
                continue
            break
        if any(o.key == "hiring.job_board" for o in out):
            break

    roles: list[str] = []
    role_page: Page | None = None
    for page in careers or [p for p in pages if p.category in ("home", "about", "team")]:
        for match in TECH_ROLE.finditer(page.text):
            title = " ".join(match.group(0).split()).title()
            if title not in roles:
                roles.append(title)
                role_page = role_page or page
    if roles and role_page is not None and careers:
        out.append(
            Observation(
                Area.HIRING,
                "hiring.tech_roles",
                roles[:20],
                role_page.url,
                excerpt(role_page.text, roles[0]),
                confidence=0.8,
            )
        )
    return out
