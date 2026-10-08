"""Wikidata (keyless SPARQL). An item is used only when its official website (P856) is this
company's domain and exactly one item says so."""

import json
from dataclasses import dataclass
from datetime import date
from typing import Any
from urllib.parse import urlencode

from app.providers.errors import ProviderError
from app.providers.fetch.safe_http import SafeHttpFetcher

SPARQL = "https://query.wikidata.org/sparql"
QUERY = """SELECT ?item ?itemLabel ?inception ?employees ?countryLabel ?industryLabel ?chn WHERE {{
  VALUES ?site {{ {sites} }}
  ?item wdt:P856 ?site .
  OPTIONAL {{ ?item wdt:P571 ?inception }}
  OPTIONAL {{ ?item wdt:P1128 ?employees }}
  OPTIONAL {{ ?item wdt:P17 ?country }}
  OPTIONAL {{ ?item wdt:P452 ?industry }}
  OPTIONAL {{ ?item wdt:P2622 ?chn }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
}} LIMIT 20"""
TYPES = frozenset({"application/sparql-results+json", "application/json"})


@dataclass(frozen=True)
class WikidataRecord:
    qid: str
    label: str
    inception: date | None
    employees: int | None
    country: str | None
    industries: tuple[str, ...]
    companies_house_number: str | None

    @property
    def url(self) -> str:
        return f"https://www.wikidata.org/wiki/{self.qid}"


def query_for(domain: str) -> str:
    variants = [
        f"<{scheme}://{host}{slash}>"
        for scheme in ("https", "http")
        for host in (domain, f"www.{domain}")
        for slash in ("", "/")
    ]
    return QUERY.format(sites=" ".join(variants))


def _value(binding: dict[str, Any], name: str) -> str | None:
    cell = binding.get(name)
    return str(cell["value"]) if isinstance(cell, dict) and "value" in cell else None


def parse(data: Any) -> WikidataRecord | None:
    """One record, or None when no item or several different items claim the website."""
    rows = data.get("results", {}).get("bindings", []) if isinstance(data, dict) else []
    items = {(_value(r, "item") or "").rsplit("/", 1)[-1] for r in rows if _value(r, "item")}
    if len(items) != 1:
        return None
    qid = items.pop()
    first = rows[0]
    inception = _value(first, "inception")
    employees = _value(first, "employees")
    try:
        when = (
            date.fromisoformat(inception[:10])
            if inception and not inception.startswith("-")
            else None
        )
    except ValueError:
        when = None
    try:
        staff = int(float(employees)) if employees else None
    except ValueError:
        staff = None
    industries = tuple(dict.fromkeys(v for r in rows if (v := _value(r, "industryLabel"))))
    label = _value(first, "itemLabel") or qid
    return WikidataRecord(
        qid=qid,
        label=label,
        inception=when,
        employees=staff,
        country=_value(first, "countryLabel"),
        industries=industries[:5],
        companies_house_number=_value(first, "chn"),
    )


class Wikidata:
    def __init__(self, *, enabled: bool = True, endpoint: str = SPARQL) -> None:
        self.enabled = enabled
        self.endpoint = endpoint

    async def lookup(self, fetcher: SafeHttpFetcher, domain: str) -> WikidataRecord | None:
        url = f"{self.endpoint}?{urlencode({'query': query_for(domain), 'format': 'json'})}"
        result = await fetcher.fetch(
            url, headers={"Accept": "application/sparql-results+json"}, content_types=TYPES
        )
        if result.status != 200:
            raise ProviderError(f"Wikidata returned {result.status}.", code="registry_error")
        try:
            return parse(json.loads(result.body))
        except ValueError as exc:
            raise ProviderError(
                "Wikidata returned invalid JSON.", code="registry_bad_output"
            ) from exc
