"""Outside checks of the researched site, run in the enrich stage (slice 8.2): how long its
homepage has gone unchanged in the Wayback Machine, and whether Google Safe Browsing lists it.

Each finding is an observation in the website area with its source. A check that is switched
off, unconfigured or failing is reported in the stage detail and never read as "all clear".
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.core.enums import EvidenceType, ObservationArea
from app.intelligence.stage import persist_observation
from app.intelligence.types import Observation
from app.providers.errors import ProviderError
from app.providers.fetch.safe_http import SafeHttpFetcher
from app.research.models import ResearchRun
from app.sitecheck.safebrowsing import SafeBrowsing
from app.sitecheck.wayback import PUBLIC_PAGE, Wayback

TRANSPARENCY_PAGE = "https://transparencyreport.google.com/safe-browsing/search?url={domain}"


@dataclass(frozen=True)
class SiteChecks:
    wayback: Wayback
    safe_browsing: SafeBrowsing

    @classmethod
    def from_settings(cls, settings: Settings) -> "SiteChecks":
        key = settings.safe_browsing_api_key
        return cls(
            Wayback(enabled=settings.website_archive_enabled),
            SafeBrowsing(key.get_secret_value() if key else None),
        )

    @classmethod
    def disabled(cls) -> "SiteChecks":
        return cls(Wayback(enabled=False), SafeBrowsing(None))


def _years(since: date, today: date) -> float:
    return round((today - since).days / 365.25, 1)


async def collect(
    domain: str, home_url: str, fetcher: SafeHttpFetcher, checks: SiteChecks, today: date
) -> tuple[list[Observation], dict[str, Any]]:
    found: list[Observation] = []
    report: dict[str, Any] = {"website_archive": "disabled", "safe_browsing": "not configured"}
    errors: list[str] = []

    if checks.wayback.enabled:
        try:
            record = await checks.wayback.lookup(fetcher, domain)
        except ProviderError as exc:
            report["website_archive"] = "failed"
            errors.append(f"wayback: {exc.message}")
        else:
            if record is None:
                report["website_archive"] = "never archived"
            else:
                years = _years(record.last_changed, today)
                report["website_archive"] = f"last changed {record.last_changed.isoformat()}"
                found.append(
                    Observation(
                        ObservationArea.WEBSITE,
                        "website.archive",
                        {
                            "first_captured": record.first_captured.isoformat(),
                            "last_changed": record.last_changed.isoformat(),
                            "years_unchanged": years,
                            "recent_versions": record.recent_versions,
                        },
                        PUBLIC_PAGE.format(domain=domain),
                        f"Wayback Machine: homepage first archived {record.first_captured:%d %b %Y}"
                        f"; archived content last changed {record.last_changed:%d %b %Y} "
                        f"({years} years ago)",
                        evidence_type=EvidenceType.OTHER,
                        # Any change counts as a change, so "unchanged" is strong, "changed" weak.
                        confidence=0.8,
                    )
                )

    if checks.safe_browsing.configured:
        try:
            threats = await checks.safe_browsing.threats(home_url)
        except ProviderError as exc:
            report["safe_browsing"] = "failed"
            errors.append(f"safe browsing: {exc.message}")
        else:
            report["safe_browsing"] = ", ".join(threats) if threats else "not listed"
            found.append(
                Observation(
                    ObservationArea.WEBSITE,
                    "website.safe_browsing",
                    {"threats": threats},
                    TRANSPARENCY_PAGE.format(domain=domain),
                    f"Google Safe Browsing lists {home_url} as: {', '.join(threats)}"
                    if threats
                    else f"Google Safe Browsing does not list {home_url}",
                    evidence_type=EvidenceType.OTHER,
                    confidence=0.95,
                )
            )
    if errors:
        report["site_check_errors"] = errors
    return found, report


async def site_checks_stage(
    run_id: uuid.UUID,
    sessionmaker: async_sessionmaker[AsyncSession],
    fetcher: SafeHttpFetcher,
    checks: SiteChecks,
    today: date | None = None,
) -> dict[str, Any]:
    async with sessionmaker() as db:
        run = await db.get(ResearchRun, run_id)
        assert run is not None
        attempt, domain, home = run.retry_count, run.normalised_domain, run.input_url
    observations, report = await collect(
        domain, home, fetcher, checks, today or datetime.now(UTC).date()
    )
    async with sessionmaker() as db:
        for observation in observations:
            persist_observation(db, run_id, attempt, observation)
        await db.commit()
    return report
