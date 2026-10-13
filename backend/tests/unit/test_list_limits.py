"""Slice 7.5: no list endpoint is unbounded.

Every GET that returns a list either takes a `limit` with a maximum, or is named below with the
reason its length is bounded anyway. A new list endpoint fails this test until it does one or the
other, so the API cannot grow an endpoint that returns every row of a growing table.
"""

from typing import Any

from app.main import create_app

PREFIX = "/api/v1"
BOUNDED: dict[str, str] = {
    # Capped inside the service.
    "/accounts/{account_id}/sales-feedback": "the 200 most recent",
    "/learning/proposals": "the 50 most recent",
    "/notifications": "the 50 most recent",
    "/prospects": "the review queue is capped (QUEUE_LIMIT)",
    "/referrals": "the 200 most recent",
    "/deals": "at most 500, the board's open deals first",
    # Per account or per person, and small by nature.
    "/accounts/{account_id}/expansion": "one suggestion per detected opportunity on one account",
    "/outreach/enrollments": "must be filtered to one contact or account",
    "/saved-views": "one person's views plus the team's",
    # Summaries or fixed lists.
    "/deals/forecast": "one row per open stage",
    "/sales-feedback/kinds": "fixed list",
    "/outreach/variables": "fixed list",
    "/notifications/preferences": "one row per notification kind",
    "/system/providers": "one row per optional provider",
    "/system/backups": "one row per backup step",
    "/roles": "the seven roles",
    # Admin-curated configuration, small by design.
    "/catalogue/services": "what Verkies sells",
    "/catalogue/reference-projects": "Verkies's own reference projects",
    "/monitoring/rules": "alert rules an admin writes",
    "/outreach/sequences": "sequences an admin writes",
    "/outreach/templates": "templates an admin writes",
    # The team.
    "/team": "the people in this workspace",
    "/users": "the people in this workspace",
    "/users/invites": "pending invites, expire after 7 days",
}


def list_endpoints() -> dict[str, Any]:
    paths: dict[str, dict[str, Any]] = create_app().openapi()["paths"]
    out = {}
    for path, item in paths.items():
        op = item.get("get")
        if not op:
            continue
        schema = (
            op.get("responses", {})
            .get("200", {})
            .get("content", {})
            .get("application/json", {})
            .get("schema", {})
        )
        if schema.get("type") == "array":
            out[path.removeprefix(PREFIX)] = op
    return out


def test_every_list_endpoint_is_bounded() -> None:
    endpoints = list_endpoints()
    assert len(endpoints) > 30
    unbounded = []
    for path, op in endpoints.items():
        limit = next((p for p in op.get("parameters", []) if p["name"] == "limit"), None)
        maximum = (limit or {}).get("schema", {}).get("maximum")
        if maximum is None and path not in BOUNDED:
            unbounded.append(path)
        if maximum is not None and maximum > 1000:
            unbounded.append(f"{path} (limit up to {maximum})")
    assert unbounded == []


def test_the_bounded_list_names_only_real_endpoints() -> None:
    assert set(BOUNDED) <= set(list_endpoints())
