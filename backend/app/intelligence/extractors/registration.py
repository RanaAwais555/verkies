"""The company's registered number, as printed on its own site. UK companies must show it
(Companies Act 2006; Company, LLP and Business Names Regulations 2015), usually in the footer,
so an exact registry lookup needs no name guessing."""

import re

from app.intelligence.types import Area, Observation, Page, SiteContext, excerpt

# "Company number 01234567", "Registered in England and Wales No. SC123456", "Reg. No: OC301234"
PREFIX = r"(?:SC|NI|OC|SO|NC|NL|R0|LP|SL|FC|GE|IP|RC|SP|SR|SZ|ZC)"
NUMBER = rf"({PREFIX}\d{{6}}|\d{{6,8}})"
PATTERNS = (
    re.compile(
        r"\b(?:company|registration|registered|reg\.?)\s*(?:no\.?|number|num\.?|#)\s*[:.]?\s*"
        + NUMBER
        + r"\b",
        re.I,
    ),
    re.compile(
        r"\bregistered in (?:england(?: (?:and|&) wales)?|wales|scotland|northern ireland)"
        r"[^0-9]{0,40}?" + NUMBER + r"\b",
        re.I,
    ),
)
JURISDICTION = re.compile(
    r"\bregistered in (england(?: (?:and|&) wales)?|wales|scotland|northern ireland)", re.I
)


def normalise(number: str) -> str:
    """Companies House form: 8 characters, digits zero-padded."""
    number = number.upper()
    return number.zfill(8) if number.isdigit() else number


def extract(pages: list[Page], ctx: SiteContext) -> list[Observation]:
    ordered = sorted(pages, key=lambda p: p.category not in ("home", "contact", "about"))
    for page in ordered:
        text = page.text
        for pattern in PATTERNS:
            match = pattern.search(text)
            if not match:
                continue
            where = JURISDICTION.search(text)
            return [
                Observation(
                    Area.COMPANY,
                    "company.registration_number",
                    {
                        "number": normalise(match.group(1)),
                        "jurisdiction": " ".join(where.group(1).split()).title() if where else None,
                    },
                    page.url,
                    excerpt(text, match.group(0), 160),
                    confidence=0.9,
                )
            ]
    return []
