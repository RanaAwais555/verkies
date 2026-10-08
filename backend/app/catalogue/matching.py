"""Service matching (master context §11): at most three confirmed services, each backed by a
detected opportunity.

primary   - the service answering the strongest opportunity
secondary - a different service answering another opportunity (confidence >= 0.5)
expansion - a further service answering another opportunity (confidence >= 0.4): the likely
            next step after the first project (land and expand)

Never lists services without evidence: no opportunity, no match.
"""

from dataclasses import dataclass

from app.core.enums import ServiceSlot
from app.opportunities.detectors import Candidate

SECONDARY_MIN = 0.5
EXPANSION_MIN = 0.4


@dataclass(frozen=True)
class ServiceInfo:
    key: str
    name: str
    solves: tuple[str, ...]


@dataclass(frozen=True)
class Match:
    slot: ServiceSlot
    service: ServiceInfo
    candidate: Candidate
    confidence: float
    rationale: str


def match_services(candidates: list[Candidate], services: list[ServiceInfo]) -> list[Match]:
    """services must already be the confirmed, active catalogue, in preference order."""
    matches: list[Match] = []
    used: set[str] = set()
    slots = [
        (ServiceSlot.PRIMARY, 0.0),
        (ServiceSlot.SECONDARY, SECONDARY_MIN),
        (ServiceSlot.EXPANSION, EXPANSION_MIN),
    ]
    remaining = list(candidates)
    for slot, minimum in slots:
        found = _next(remaining, services, used, minimum)
        if found is None:
            continue
        candidate, service = found
        used.add(service.key)
        remaining.remove(candidate)
        matches.append(
            Match(
                slot=slot,
                service=service,
                candidate=candidate,
                confidence=candidate.confidence,
                rationale=(
                    f"{service.name} answers: {candidate.title} ({candidate.confidence:.2f})."
                ),
            )
        )
    return matches


def _next(
    candidates: list[Candidate], services: list[ServiceInfo], used: set[str], minimum: float
) -> tuple[Candidate, ServiceInfo] | None:
    for candidate in candidates:
        if candidate.confidence < minimum:
            continue
        for service in services:
            if candidate.category in service.solves and service.key not in used:
                return candidate, service
    return None
