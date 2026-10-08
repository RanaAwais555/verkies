"""Buying-signal types and strengths (master context §9). Keyword rules only: a title either
clearly says what happened or the item is not a signal."""

import re

from app.intelligence.extractors.hiring import TECH_ROLE

VERY_STRONG = "very_strong"
STRONG = "strong"
MEDIUM = "medium"

# signal type -> strength
STRENGTH = {
    "developer_hiring": VERY_STRONG,
    "cto_hiring": VERY_STRONG,
    "product_hiring": VERY_STRONG,
    "funding": VERY_STRONG,
    "product_launch": VERY_STRONG,
    "new_leader": STRONG,
    "acquisition": STRONG,
    "expansion": STRONG,
    "new_service": STRONG,
    "hiring": MEDIUM,
    "rebrand": MEDIUM,  # change of company name (often a new website follows)
    "financing": MEDIUM,  # a charge registered: secured lending
}

CTO = re.compile(
    r"\b(cto|chief technology officer|vp (?:of )?engineering|head of (?:engineering|technology))\b",
    re.I,
)
PRODUCT = re.compile(
    r"\b(product manager|head of product|product owner|product lead|chief product officer|cpo)\b",
    re.I,
)
NEWS: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (kind, re.compile(pattern, re.I))
    for kind, pattern in (
        (
            "funding",
            r"\b(raises?|raised|funding|seed round|series [a-d]|investment round"
            r"|secures? £|secures? \$|secures? €)\b",
        ),
        ("acquisition", r"\b(acquires?|acquired|acquisition|merges? with|merger)\b"),
        (
            "new_leader",
            r"\b(appoints?|appointed|welcomes? .{0,40} as|joins as"
            r"|new (?:ceo|cto|coo|cmo|chief))\b",
        ),
        ("expansion", r"\b(expands?|expansion|new office|opens? (?:in|a new)|launches? in)\b"),
        ("new_service", r"\b(new service|now offer(?:s|ing)?)\b"),
        (
            "product_launch",
            r"\b(launch(?:es|ed)?|introducing|now available|unveils?"
            r"|new app|new platform|goes live)\b",
        ),
    )
)


def job_signal(title: str) -> str:
    if CTO.search(title):
        return "cto_hiring"
    if PRODUCT.search(title):
        return "product_hiring"
    if TECH_ROLE.search(title):
        return "developer_hiring"
    return "hiring"


def news_signal(title: str) -> str | None:
    for kind, pattern in NEWS:
        if pattern.search(title):
            return kind
    return None
