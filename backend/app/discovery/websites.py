"""Finding the website of a company found in the register (Companies House discovery).

The register has no websites, so this searches the web for the company and accepts a site only
when its homepage shows the same registered number: UK companies must print it on their
website, so a match is evidence, not a guess. Companies without such a site are listed as
"no website" with the reason, never given a plausible-looking domain.
"""

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auth.models import User
from app.core.enums import CandidateStatus, DiscoveryStatus
from app.discovery import service
from app.discovery.models import DiscoveredCompany, DiscoveryJob
from app.discovery.web_search import candidates as web_candidates
from app.intelligence.extractors.registration import extract as registration
from app.intelligence.extractors.registration import normalise
from app.intelligence.types import Page, SiteContext
from app.providers.errors import ProviderError, ProviderUnavailable
from app.providers.fetch.types import HTML_TYPES
from app.providers.search import SearchProvider
from app.research.crawler import PageSource
from app.signals.stage import robots_for

MAX_CANDIDATES = 4
REGISTRY_MAPPING = {"name": "name", "website": "website", "notes": "notes"}
LEGAL_SUFFIXES = (" LIMITED", " LTD", " PLC", " LLP", " LTD.", " LIMITED.")


def search_name(name: str) -> str:
    """ "BRIGHT LEGAL LTD" -> "Bright Legal": what the company calls itself on its site."""
    upper = name.upper().strip()
    for suffix in LEGAL_SUFFIXES:
        if upper.endswith(suffix):
            name = name[: -len(suffix)]
            break
    return name.strip().title()


async def find_website(
    *,
    name: str,
    number: str,
    locality: str | None,
    search: SearchProvider,
    source: PageSource,
) -> tuple[str | None, str]:
    """(homepage URL, note). The URL is set only when that homepage shows `number`."""
    query = " ".join(p for p in (f'"{search_name(name)}"', locality) if p)
    try:
        results = await search.search(query, pages=1, language="en-GB")
    except ProviderUnavailable:
        return None, "Web search is not set up, so no website could be looked for."
    except ProviderError as exc:
        return None, f"Web search failed: {exc.message}"
    sites = web_candidates(results)[:MAX_CANDIDATES]
    wanted = normalise(number)
    for site in sites:
        url = site["website"]
        try:
            if not (await robots_for(source, url)).allows(url):
                continue
            fetched = await source.fetch(url, content_types=HTML_TYPES)
        except ProviderError:
            continue
        result = fetched.result
        if result.status != 200:
            continue
        page = Page(result.final_url, result.text(), "home")
        found = registration([page], SiteContext(result.final_url, "parsed"))
        if found and found[0].value["number"] == wanted:
            return result.final_url, f"The homepage shows company number {number}."
    return None, (
        f"No website showing company number {number} among {len(sites)} search result(s)."
    )


async def find_websites(
    job_id: uuid.UUID,
    sessionmaker: async_sessionmaker[AsyncSession],
    search: SearchProvider,
    source: PageSource,
) -> dict[str, Any]:
    """Worker: resolve every waiting row of a registry discovery job, then check the job like
    an import. Progress is committed row by row so the page can show it."""
    async with sessionmaker() as db:
        rows = list(
            (
                await db.execute(
                    select(DiscoveredCompany.id)
                    .where(
                        DiscoveredCompany.discovery_job_id == job_id,
                        DiscoveredCompany.status == CandidateStatus.FINDING_WEBSITE,
                    )
                    .order_by(DiscoveredCompany.row_number)
                )
            ).scalars()
        )
        known = await service.accounts_by_number(
            db,
            {
                str(r.raw.get("number"))
                for r in (
                    await db.execute(
                        select(DiscoveredCompany).where(
                            DiscoveredCompany.discovery_job_id == job_id
                        )
                    )
                ).scalars()
            },
        )
    found = 0
    for row_id in rows:
        async with sessionmaker() as db:
            row = await db.get(DiscoveredCompany, row_id)
            if row is None:
                continue
            number = str(row.raw.get("number") or "")
            if number in known:
                url, note = None, "Already an account."
            else:
                url, note = await find_website(
                    name=str(row.raw.get("name") or ""),
                    number=number,
                    locality=row.raw.get("locality"),
                    search=search,
                    source=source,
                )
            row.raw = {**row.raw, "website": url or "", "website_note": note}
            row.status = CandidateStatus.PENDING
            found += 1 if url else 0
            await db.commit()
    async with sessionmaker() as db:
        job = await db.get(DiscoveryJob, job_id)
        if job is None:
            return {"rows": len(rows), "websites": found}
        creator = await db.get(User, job.created_by_id)
        assert creator is not None
        await service.check(db, user=creator, job=job, mapping=REGISTRY_MAPPING)
        job.status = DiscoveryStatus.CHECKED
        await db.commit()
    return {"rows": len(rows), "websites": found}
