"""Named people from every source: the company's own pages (`company.person`) and the
official register (`registry.officer`). The same person found in both counts once."""

from app.intelligence.facts import Fact, Facts


def _key(name: str) -> tuple[str, str]:
    words = [w for w in name.lower().replace(".", " ").split() if w]
    return (words[0], words[-1]) if words else ("", "")


def same_person(a: str, b: str) -> bool:
    """First and last name agree ("Amelia Hart" and "Amelia Jane Hart")."""
    return _key(a) == _key(b) and _key(a) != ("", "")


def named_people(facts: Facts) -> list[Fact]:
    """Site people first, then registered officers not already named on the site. Officers
    are given the shape of site people: {"name", "title", "source"}."""
    site = facts.all("company.person")
    people = list(site)
    for officer in facts.all("registry.officer"):
        name = str(officer.value.get("name", ""))
        if not name or any(same_person(name, str(p.value.get("name", ""))) for p in people):
            continue
        people.append(
            Fact(
                officer.key,
                {"name": name, "title": officer.value.get("role"), "source": "companies_house"},
                officer.confidence,
                officer.evidence_id,
                officer.source_url,
                officer.excerpt,
            )
        )
    return people
