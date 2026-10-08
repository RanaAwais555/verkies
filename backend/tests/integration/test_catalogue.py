"""Catalogue reads, the team list, and completing a reference-project profile."""

from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, text

from tests.integration.conftest import ApiClient, make_user

pytestmark = pytest.mark.integration


def test_team_and_catalogue_are_readable_by_any_member(api: ApiClient, engine: Engine) -> None:
    make_user(engine, "v@verkies.test", ["viewer"], name="Val Viewer")
    make_user(engine, "gone@verkies.test", ["viewer"], name="Gone", is_active=False)
    assert api.get("/team").status_code == 401
    api.login("v@verkies.test")
    assert [m["name"] for m in api.get("/team").json()] == ["Val Viewer"]
    services = api.get("/catalogue/services").json()
    assert len(services) == 15 and all(s["confirmed"] for s in services)
    projects = api.get("/catalogue/reference-projects").json()
    assert projects and not any(p["profile_complete"] for p in projects)
    denied = api.send("PATCH", f"/catalogue/reference-projects/{projects[0]['id']}", json={})
    assert denied.status_code == 403


@pytest.fixture
def restore_references(engine: Engine) -> Iterator[None]:
    """Reference projects are seed data the cleanup keeps, so put them back as they were."""
    with engine.connect() as conn:
        projects = conn.execute(text("SELECT * FROM reference_projects")).mappings().all()
        links = conn.execute(text("SELECT * FROM reference_project_services")).mappings().all()
    yield
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM reference_project_services"))
        for row in projects:
            sets = ", ".join(f"{k} = :{k}" for k in row if k != "id")
            conn.execute(text(f"UPDATE reference_projects SET {sets} WHERE id = :id"), dict(row))  # noqa: S608
        for link in links:
            conn.execute(
                text(
                    "INSERT INTO reference_project_services (reference_project_id, service_id)"
                    " VALUES (:reference_project_id, :service_id)"
                ),
                dict(link),
            )


@pytest.mark.usefixtures("restore_references")
def test_admin_completes_a_reference_profile(api: ApiClient, engine: Engine) -> None:
    make_user(engine, "admin@verkies.test", ["admin"])
    api.login("admin@verkies.test")
    project = next(
        p
        for p in api.get("/catalogue/reference-projects").json()
        if p["name"] == "Wesbridge Associates"
    )
    path = f"/catalogue/reference-projects/{project['id']}"

    incomplete = api.send("PATCH", path, json={"profile_complete": True, "services": []})
    assert incomplete.status_code == 422
    unknown = api.send("PATCH", path, json={"services": ["nope"]})
    assert unknown.status_code == 422 and "nope" in unknown.json()["error"]["message"]

    done = api.send(
        "PATCH",
        path,
        json={
            "industry": "UK immigration advice",
            "problem": "Manual intake and a broken website",
            "services": ["web_dev", "crm_portal"],
            "profile_complete": True,
        },
    )
    assert done.status_code == 200, done.text
    body = done.json()
    assert body["profile_complete"] and body["services"] == ["crm_portal", "web_dev"]
    entry = api.get("/audit", params={"object_id": project["id"]}).json()["items"][0]
    assert entry["action"] == "reference_project.updated"
    assert entry["new_value"]["profile_complete"] is True


def test_provider_status_shows_degraded_modes_without_leaking_keys(
    api: ApiClient, engine: Engine
) -> None:
    make_user(engine, "v@verkies.test", ["viewer"])
    assert api.get("/system/providers").status_code == 401
    api.login("v@verkies.test")
    found = {p["name"]: p for p in api.get("/system/providers").json()}
    assert found["Companies House"]["status"] == "degraded"
    assert "VROS_COMPANIES_HOUSE_API_KEY" in found["Companies House"]["detail"]
    assert found["AI writing"]["status"] == "off"
