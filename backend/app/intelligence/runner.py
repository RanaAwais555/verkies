"""Runs every extractor over a run's pages and merges duplicate observations."""

import logging
from collections.abc import Callable

from app.intelligence.extractors import (
    company,
    conversion,
    hiring,
    product,
    seo,
    technology,
    website,
)
from app.intelligence.types import Observation, Page, SiteContext

logger = logging.getLogger(__name__)

Extractor = Callable[[list[Page], SiteContext], list[Observation]]
EXTRACTORS: dict[str, Extractor] = {
    "website": website.extract,
    "seo": seo.extract,
    "conversion": conversion.extract,
    "product": product.extract,
    "technology": technology.extract,
    "company": company.extract,
    "hiring": hiring.extract,
}


def analyse(pages: list[Page], ctx: SiteContext) -> tuple[list[Observation], list[str]]:
    """(observations, names of extractors that failed). One broken extractor never loses the
    others' findings; the failure is reported, not hidden."""
    if not pages:
        return [], []
    merged: dict[tuple[str, str], Observation] = {}
    failed: list[str] = []
    for name, extractor in EXTRACTORS.items():
        try:
            found = extractor(pages, ctx)
        except Exception:
            logger.exception("extractor failed", extra={"extractor": name})
            failed.append(name)
            continue
        for observation in found:
            key = observation.identity()
            if key in merged:
                existing = merged[key]
                if observation.confidence > existing.confidence:
                    # Keep the strongest evidence for the same fact.
                    existing.confidence = observation.confidence
                    existing.source_url = observation.source_url
                    existing.excerpt = observation.excerpt
                    existing.evidence_type = observation.evidence_type
                for url in [observation.source_url, *observation.seen_on]:
                    if url not in existing.seen_on:
                        existing.seen_on.append(url)
            else:
                if observation.source_url not in observation.seen_on:
                    observation.seen_on.insert(0, observation.source_url)
                merged[key] = observation
    return list(merged.values()), failed
