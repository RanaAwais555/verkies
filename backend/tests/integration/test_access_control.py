"""Slice 7.4: every API route is covered by an access check.

The routes come from the app itself (its OpenAPI schema), so a new route is tested the day it is
added: unless it is listed below as public, open to anyone signed in, or personal, it must refuse
a stranger (401), a signed-in person with no role (403), and, if it changes anything, a Viewer
(403). A route that is meant to be different has to be added to a list here, on purpose.
"""

import re
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from sqlalchemy import Engine, text

from app.main import create_app
from tests.integration.conftest import ApiClient, make_user
from tests.integration.test_leads import account

pytestmark = pytest.mark.integration

PREFIX = "/api/v1"
# No sign-in needed.
PUBLIC = {
    ("GET", "/health/live"),
    ("GET", "/health/ready"),
    ("POST", "/auth/login"),
    ("POST", "/auth/invites/inspect"),
    ("POST", "/auth/invites/accept"),
}
# Anyone signed in, whatever their role: their own session, password and notifications; which
# optional providers are on; and the reference lists every screen needs (the team, for owner
# pickers; the services and reference projects shown under Settings). All read-only.
SIGNED_IN = {
    ("GET", "/team"),
    ("GET", "/catalogue/services"),
    ("GET", "/catalogue/reference-projects"),
    ("GET", "/auth/me"),
    ("POST", "/auth/logout"),
    ("POST", "/auth/password"),
    ("GET", "/notifications"),
    ("GET", "/notifications/count"),
    ("POST", "/notifications/{notification_id}/read"),
    ("POST", "/notifications/read-all"),
    ("GET", "/notifications/preferences"),
    ("PUT", "/notifications/preferences"),
    ("GET", "/system/providers"),
}
# Changes only the person's own things, so a Viewer may do them.
PERSONAL = {
    ("PUT", "/accounts/{account_id}/watch"),
    ("DELETE", "/accounts/{account_id}/watch"),
    ("POST", "/saved-views"),
    ("DELETE", "/saved-views/{view_id}"),
}
SAFE = {"GET", "HEAD", "OPTIONS"}


def operations() -> list[tuple[str, str]]:
    paths: dict[str, dict[str, Any]] = create_app().openapi()["paths"]
    return sorted(
        (method.upper(), path.removeprefix(PREFIX))
        for path, item in paths.items()
        for method in item
        if method in {"get", "post", "put", "patch", "delete"}
    )


OPERATIONS = operations()


def concrete(path: str) -> str:
    """Fill each path parameter with a random id: access is decided before any lookup."""
    return PREFIX + re.sub(r"\{[^}]+\}", lambda _: str(uuid.uuid4()), path)


def call(api: ApiClient, method: str, path: str) -> int:
    body = None if method in SAFE else {}
    return api.send(method, concrete(path).removeprefix(PREFIX), json=body).status_code


def test_the_lists_name_only_real_routes() -> None:
    known = set(OPERATIONS)
    assert known >= PUBLIC and known >= SIGNED_IN and known >= PERSONAL
    assert len(OPERATIONS) > 100  # the schema really was read


def refused(api: ApiClient, expected: int, ops: list[tuple[str, str]]) -> list[str]:
    """Every operation that did not answer `expected`, as "METHOD /path -> status"."""
    wrong = []
    for method, path in ops:
        status = call(api, method, path)
        if status != expected:
            wrong.append(f"{method} {path} -> {status}")
    return wrong


def test_strangers_are_refused(api: ApiClient) -> None:
    assert refused(api, 401, [op for op in OPERATIONS if op not in PUBLIC]) == []


def test_a_person_without_a_role_is_refused(engine: Engine, api: ApiClient) -> None:
    make_user(engine, "nora@verkies.test", [], name="Nora Norole")
    api.login("nora@verkies.test")
    assert refused(api, 403, [op for op in OPERATIONS if op not in PUBLIC | SIGNED_IN]) == []


@pytest.fixture
def viewer(engine: Engine, api: ApiClient) -> Iterator[ApiClient]:
    make_user(engine, "vic@verkies.test", ["viewer"], name="Vic Viewer")
    api.login("vic@verkies.test")
    yield api


def test_a_viewer_cannot_change_anything(viewer: ApiClient) -> None:
    changes = [
        op for op in OPERATIONS if op[0] not in SAFE and op not in PUBLIC | SIGNED_IN | PERSONAL
    ]
    assert len(changes) > 50
    assert refused(viewer, 403, changes) == []


def test_a_viewer_can_still_read_and_do_personal_things(engine: Engine, viewer: ApiClient) -> None:
    owner = make_user(engine, "ada@verkies.test", ["admin"], name="Ada Admin")
    account_id = account(engine, "Acme Legal", domain="acme.test", owner=owner)
    assert viewer.get("/accounts").status_code == 200
    assert viewer.get(f"/accounts/{account_id}").status_code == 200
    assert viewer.send("PUT", f"/accounts/{account_id}/watch").status_code == 204
    refused = viewer.send("POST", "/tasks", json={"account_id": str(account_id), "title": "Call"})
    assert refused.status_code == 403
    assert refused.json()["error"]["message"] == "Your role can view records but not change them."


def test_every_role_but_viewer_may_change_records(engine: Engine) -> None:
    with engine.connect() as conn:
        holders = set(
            conn.execute(
                text(
                    "SELECT r.key FROM roles r JOIN role_permissions rp ON rp.role_id = r.id"
                    " JOIN permissions p ON p.id = rp.permission_id WHERE p.key = 'records.write'"
                )
            ).scalars()
        )
        roles = set(conn.execute(text("SELECT key FROM roles")).scalars())
    assert holders == roles - {"viewer"}


def test_account_routes_hide_other_peoples_accounts_from_a_salesperson(
    engine: Engine, api: ApiClient
) -> None:
    """Record level: for every route scoped to an account, someone else's account answers
    exactly as an account that does not exist would (usually 404; 403 where the role may not use
    the route at all), so nothing reveals it exists, for reads and changes alike."""
    owner = make_user(engine, "ada@verkies.test", ["admin"], name="Ada Admin")
    theirs = account(engine, "Acme Legal", domain="acme.test", owner=owner)
    make_user(engine, "sam@verkies.test", ["salesperson"], name="Sam Seller")
    api.login("sam@verkies.test")
    scoped = [(m, p) for m, p in OPERATIONS if p.startswith("/accounts/{account_id}")]
    assert len(scoped) > 15
    wrong = []
    for method, path in scoped:
        answers = []
        for target in (theirs, uuid.uuid4()):
            url = concrete(path.replace("{account_id}", str(target))).removeprefix(PREFIX)
            answers.append(api.send(method, url, json=None if method in SAFE else {}).status_code)
        if answers[0] != answers[1] or answers[0] < 400:
            wrong.append(f"{method} {path}: theirs {answers[0]}, none {answers[1]}")
    assert wrong == []
    assert api.get(f"/accounts/{theirs}").status_code == 404
