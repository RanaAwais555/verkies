"""A read-only view over a run's observations, shared by detectors, ICP and scoring.

Every judgement built on Facts can name the evidence it used: each Fact carries the ID of
the evidence row behind it, and helpers return those IDs alongside values.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Fact:
    key: str
    value: Any
    confidence: float
    evidence_id: str
    source_url: str


class Facts:
    def __init__(self, facts: Iterable[Fact]) -> None:
        self._by_key: dict[str, list[Fact]] = {}
        for fact in facts:
            self._by_key.setdefault(fact.key, []).append(fact)

    def all(self, key: str) -> list[Fact]:
        return list(self._by_key.get(key, []))

    def first(self, key: str) -> Fact | None:
        found = self._by_key.get(key)
        return found[0] if found else None

    def value(self, key: str, default: Any = None) -> Any:
        fact = self.first(key)
        return fact.value if fact is not None else default

    def has(self, key: str) -> bool:
        return key in self._by_key

    def is_true(self, key: str) -> bool:
        return self.value(key) is True

    def is_absent(self, key: str) -> bool:
        """Recorded as checked-and-not-found (False, None or an empty list), not merely missing."""
        return self.has(key) and self.value(key) in (False, None, [])

    def present(self, key: str) -> bool:
        """Recorded with a real value (True, a name, a non-empty list...)."""
        return self.has(key) and self.value(key) not in (False, None, [])

    def evidence(self, *keys: str) -> list[str]:
        ids: list[str] = []
        for key in keys:
            for fact in self._by_key.get(key, []):
                if fact.evidence_id not in ids:
                    ids.append(fact.evidence_id)
        return ids

    def technologies(self) -> dict[str, Fact]:
        return {f.value["name"]: f for f in self.all("technology.detected")}

    def keys(self) -> list[str]:
        return list(self._by_key)

    def __iter__(self):  # type: ignore[no-untyped-def]
        for facts in self._by_key.values():
            yield from facts

    def __len__(self) -> int:
        return sum(len(v) for v in self._by_key.values())


def facts_from_observations(observations: Iterable[Any]) -> Facts:
    """Build Facts from extractor Observations (tests and fixtures). Evidence IDs are
    synthetic but stable: "<key>#<n>"."""
    built: list[Fact] = []
    for n, o in enumerate(observations):
        built.append(Fact(o.key, o.value, o.confidence, f"{o.key}#{n}", o.source_url))
    return Facts(built)
