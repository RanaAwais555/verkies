"""Team access end to end: login, sessions, CSRF, invites, RBAC, admin guard, audit."""

import re
from collections.abc import Callable

import pytest
from sqlalchemy import Engine, text

from app.cli import main as cli_main
from app.config import get_settings
from app.db import get_engine, get_sessionmaker
from tests.integration.conftest import PASSWORD, ApiClient, make_user

pytestmark = pytest.mark.integration

ADMIN = "admin@verkies.test"


def _audit_actions(engine: Engine) -> list[str]:
    with engine.connect() as conn:
        return list(
            conn.execute(text("SELECT action FROM audit_log ORDER BY occurred_at")).scalars()
        )


# --- login and sessions -------------------------------------------------------------------


def test_login_sets_httponly_session_and_returns_profile(api: ApiClient, engine: Engine) -> None:
    make_user(engine, ADMIN, ["admin"], name="Ada")
    response = api.http.post("/api/v1/auth/login", json={"email": ADMIN, "password": PASSWORD})
    assert response.status_code == 200
    body = response.json()
    assert body["user"]["email"] == ADMIN
    assert "users.manage" in body["user"]["permissions"]
    cookies = response.headers.get_list("set-cookie")
    session_cookie = next(c for c in cookies if c.startswith("vros_session="))
    assert "HttpOnly" in session_cookie and "SameSite=lax" in session_cookie
    assert api.get("/auth/me").json()["user"]["name"] == "Ada"


def test_email_is_case_insensitive(api: ApiClient, engine: Engine) -> None:
    make_user(engine, ADMIN, ["admin"])
    api.login(ADMIN.upper())


@pytest.mark.parametrize(
    ("email", "password"), [(ADMIN, "wrong password!!"), ("nobody@verkies.test", PASSWORD)]
)
def test_failed_login_is_generic(api: ApiClient, engine: Engine, email: str, password: str) -> None:
    make_user(engine, ADMIN, ["admin"])
    response = api.http.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 401
    assert response.json()["error"]["message"] == "Invalid email or password."


def test_account_locks_after_repeated_failures(api: ApiClient, engine: Engine) -> None:
    make_user(engine, ADMIN, ["admin"])
    for _ in range(get_settings().login_max_failures):
        api.http.post("/api/v1/auth/login", json={"email": ADMIN, "password": "wrong password!!"})
    locked = api.http.post("/api/v1/auth/login", json={"email": ADMIN, "password": PASSWORD})
    assert locked.status_code == 401  # even the right password is refused while locked
    with engine.begin() as conn:
        conn.execute(text("UPDATE users SET locked_until = now() - interval '1 second'"))
    api.login(ADMIN)
    assert (
        _audit_actions(engine).count("auth.login_failed") == get_settings().login_max_failures + 1
    )


def test_inactive_user_cannot_sign_in(api: ApiClient, engine: Engine) -> None:
    make_user(engine, ADMIN, ["admin"], is_active=False)
    response = api.http.post("/api/v1/auth/login", json={"email": ADMIN, "password": PASSWORD})
    assert response.status_code == 401


def test_requests_without_session_are_rejected(api: ApiClient) -> None:
    assert api.get("/auth/me").status_code == 401
    assert api.get("/users").status_code == 401


def test_state_changes_require_csrf_token(api: ApiClient, engine: Engine) -> None:
    make_user(engine, ADMIN, ["admin"])
    api.login(ADMIN)
    missing = api.send("POST", "/auth/logout", headers={"X-CSRF-Token": ""})
    assert missing.status_code == 403
    assert missing.json()["error"]["code"] == "csrf_failed"
    wrong = api.send("POST", "/auth/logout", headers={"X-CSRF-Token": "forged"})
    assert wrong.status_code == 403
    assert api.send("POST", "/auth/logout").status_code == 204
    assert api.get("/auth/me").status_code == 401


def test_idle_session_expires(api: ApiClient, engine: Engine) -> None:
    make_user(engine, ADMIN, ["admin"])
    api.login(ADMIN)
    idle = get_settings().session_idle_minutes + 1
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE user_sessions SET last_seen_at = now() - make_interval(mins => :m)"),
            {"m": idle},
        )
    assert api.get("/auth/me").status_code == 401


def test_session_token_is_stored_only_as_hash(api: ApiClient, engine: Engine) -> None:
    make_user(engine, ADMIN, ["admin"])
    api.login(ADMIN)
    token = api.http.cookies.get("vros_session")
    with engine.connect() as conn:
        stored = conn.execute(text("SELECT token_hash FROM user_sessions")).scalar_one()
    assert token and stored != token and len(stored) == 64


def test_password_change_signs_out_other_sessions(
    api: ApiClient, make_api: Callable[[], ApiClient], engine: Engine
) -> None:
    make_user(engine, ADMIN, ["admin"])
    other = make_api()
    api.login(ADMIN)
    other.login(ADMIN)
    weak = api.send(
        "POST", "/auth/password", json={"current_password": PASSWORD, "new_password": "short"}
    )
    assert weak.status_code == 422
    new = "a much longer new passphrase"
    changed = api.send(
        "POST", "/auth/password", json={"current_password": PASSWORD, "new_password": new}
    )
    assert changed.status_code == 204
    assert api.get("/auth/me").status_code == 200
    assert other.get("/auth/me").status_code == 401
    api.send("POST", "/auth/logout")
    api.login(ADMIN, new)


# --- invites ------------------------------------------------------------------------------


def _invite(api: ApiClient, email: str, roles: list[str]) -> str:
    response = api.send("POST", "/users/invites", json={"email": email, "roles": roles})
    assert response.status_code == 201, response.text
    url = response.json()["invite_url"]
    match = re.fullmatch(r"http://localhost:3000/invite#token=([\w-]+)", url)
    assert match, url
    return match.group(1)


def test_invite_flow_creates_member_with_invited_roles(
    api: ApiClient, make_api: Callable[[], ApiClient], engine: Engine
) -> None:
    make_user(engine, ADMIN, ["admin"])
    api.login(ADMIN)
    token = _invite(api, "sam@verkies.test", ["salesperson"])

    newcomer = make_api()
    info = newcomer.http.post("/api/v1/auth/invites/inspect", json={"token": token})
    assert info.json()["email"] == "sam@verkies.test"
    assert info.json()["roles"] == ["salesperson"]

    weak = newcomer.http.post(
        "/api/v1/auth/invites/accept", json={"token": token, "name": "Sam", "password": "short"}
    )
    assert weak.status_code == 422
    accepted = newcomer.http.post(
        "/api/v1/auth/invites/accept",
        json={"token": token, "name": "Sam", "password": "sam has a long passphrase"},
    )
    assert accepted.status_code == 200
    assert accepted.json()["user"]["roles"] == ["salesperson"]
    assert newcomer.get("/auth/me").status_code == 200

    reused = make_api().http.post(
        "/api/v1/auth/invites/accept",
        json={"token": token, "name": "Eve", "password": "eve has a long passphrase"},
    )
    assert reused.status_code == 404
    assert "user.created" in _audit_actions(engine)
    assert "invite.created" in _audit_actions(engine)


def test_expired_and_revoked_invites_do_not_work(api: ApiClient, engine: Engine) -> None:
    make_user(engine, ADMIN, ["admin"])
    api.login(ADMIN)
    expired = _invite(api, "late@verkies.test", ["viewer"])
    with engine.begin() as conn:
        conn.execute(text("UPDATE invites SET expires_at = now() - interval '1 minute'"))
    assert api.http.post("/api/v1/auth/invites/inspect", json={"token": expired}).status_code == 404

    revoked = _invite(api, "gone@verkies.test", ["viewer"])
    invite_id = next(
        i["id"] for i in api.get("/users/invites").json() if i["email"] == "gone@verkies.test"
    )
    assert api.send("DELETE", f"/users/invites/{invite_id}").status_code == 204
    assert api.http.post("/api/v1/auth/invites/inspect", json={"token": revoked}).status_code == 404


def test_reinviting_replaces_the_pending_invite(api: ApiClient, engine: Engine) -> None:
    make_user(engine, ADMIN, ["admin"])
    api.login(ADMIN)
    first = _invite(api, "sam@verkies.test", ["viewer"])
    _invite(api, "sam@verkies.test", ["salesperson"])
    assert api.http.post("/api/v1/auth/invites/inspect", json={"token": first}).status_code == 404
    pending = [i for i in api.get("/users/invites").json() if i["email"] == "sam@verkies.test"]
    assert [i["roles"] for i in pending] == [["salesperson"]]


def test_cannot_invite_existing_member_or_unknown_role(api: ApiClient, engine: Engine) -> None:
    make_user(engine, ADMIN, ["admin"])
    api.login(ADMIN)
    taken = api.send("POST", "/users/invites", json={"email": ADMIN, "roles": ["viewer"]})
    assert taken.status_code == 409
    bad = api.send("POST", "/users/invites", json={"email": "x@verkies.test", "roles": ["god"]})
    assert bad.status_code == 422


# --- RBAC and admin guard -----------------------------------------------------------------


def test_only_admins_manage_users(api: ApiClient, engine: Engine) -> None:
    make_user(engine, "sales@verkies.test", ["salesperson"])
    api.login("sales@verkies.test")
    assert api.get("/users").status_code == 403
    assert api.get("/roles").status_code == 403
    denied = api.send("POST", "/users/invites", json={"email": "x@v.test", "roles": ["admin"]})
    assert denied.status_code == 403


def test_audit_log_visible_to_managers_not_salespeople(
    api: ApiClient, make_api: Callable[[], ApiClient], engine: Engine
) -> None:
    make_user(engine, "boss@verkies.test", ["sales_manager"])
    make_user(engine, "sales@verkies.test", ["salesperson"])
    api.login("boss@verkies.test")
    assert api.get("/audit").status_code == 200
    sales = make_api()
    sales.login("sales@verkies.test")
    assert sales.get("/audit").status_code == 403


def test_last_admin_cannot_be_removed(api: ApiClient, engine: Engine) -> None:
    admin_id = make_user(engine, ADMIN, ["admin"])
    api.login(ADMIN)
    demote = api.send("PATCH", f"/users/{admin_id}", json={"roles": ["viewer"]})
    assert demote.status_code == 409
    deactivate = api.send("PATCH", f"/users/{admin_id}", json={"is_active": False})
    assert deactivate.status_code == 409


def test_deactivating_a_member_ends_their_sessions(
    api: ApiClient, make_api: Callable[[], ApiClient], engine: Engine
) -> None:
    make_user(engine, ADMIN, ["admin"])
    member_id = make_user(engine, "sam@verkies.test", ["salesperson"])
    member = make_api()
    member.login("sam@verkies.test")
    api.login(ADMIN)
    response = api.send("PATCH", f"/users/{member_id}", json={"is_active": False})
    assert response.status_code == 200
    assert response.json()["is_active"] is False
    assert member.get("/auth/me").status_code == 401
    changes = [a for a in _audit_actions(engine) if a == "user.updated"]
    assert changes == ["user.updated"]


def test_role_change_takes_effect_on_next_request(
    api: ApiClient, make_api: Callable[[], ApiClient], engine: Engine
) -> None:
    make_user(engine, ADMIN, ["admin"])
    member_id = make_user(engine, "sam@verkies.test", ["viewer"])
    member = make_api()
    member.login("sam@verkies.test")
    assert member.get("/audit").status_code == 403
    api.login(ADMIN)
    api.send("PATCH", f"/users/{member_id}", json={"roles": ["sales_manager"]})
    assert member.get("/audit").status_code == 200


# --- audit API ----------------------------------------------------------------------------


def test_audit_pagination(api: ApiClient, engine: Engine) -> None:
    make_user(engine, ADMIN, ["admin"])
    for _ in range(3):
        api.login(ADMIN)
    first = api.get("/audit", params={"limit": 2}).json()
    assert len(first["items"]) == 2 and first["next_cursor"]
    rest = api.get("/audit", params={"limit": 2, "before": first["next_cursor"]}).json()
    assert len(rest["items"]) == 1 and rest["next_cursor"] is None
    seen = {i["id"] for i in first["items"]} | {i["id"] for i in rest["items"]}
    assert len(seen) == 3
    assert api.get("/audit", params={"before": "garbage"}).status_code == 422


# --- CLI ----------------------------------------------------------------------------------


def test_cli_creates_the_first_admin(
    api: ApiClient, engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("VROS_ADMIN_PASSWORD", PASSWORD)
    assert cli_main(["create-admin", "--email", ADMIN, "--name", "Ada"]) == 0
    assert cli_main(["create-admin", "--email", ADMIN, "--name", "Ada"]) == 1  # duplicate
    # The CLI ran its own event loop; drop its engine before the app's loop uses one.
    get_engine.cache_clear()
    get_sessionmaker.cache_clear()
    me = api.login(ADMIN)
    assert me["user"]["roles"] == ["admin"]
    with engine.connect() as conn:
        source = conn.execute(
            text("SELECT source FROM audit_log WHERE action = 'user.created'")
        ).scalar_one()
    assert source == "cli"


def test_activity_on_any_endpoint_keeps_the_session_alive(api: ApiClient, engine: Engine) -> None:
    make_user(engine, ADMIN, ["admin"])
    api.login(ADMIN)
    with engine.begin() as conn:
        conn.execute(text("UPDATE user_sessions SET last_seen_at = now() - interval '1 hour'"))
    assert api.get("/users").status_code == 200  # not /auth/me
    with engine.connect() as conn:
        age = conn.execute(
            text("SELECT extract(epoch FROM now() - last_seen_at) FROM user_sessions")
        ).scalar_one()
    assert age < 60
