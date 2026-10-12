"""Slice 4.4: documents uploaded to an account and linked to its deal or project."""

import uuid
from collections.abc import Callable
from pathlib import Path

import pytest
from sqlalchemy import Engine, text

from app.config import Settings, get_settings
from app.documents.router import get_document_storage
from app.providers.storage import LocalStorage
from tests.integration.conftest import ApiClient, make_user
from tests.integration.test_clients import won_deal
from tests.integration.test_leads import account

pytestmark = pytest.mark.integration

PDF = b"%PDF-1.7\n1 0 obj << >> endobj\n%%EOF\n"


@pytest.fixture
def admin(engine: Engine, api: ApiClient, tmp_path: Path) -> uuid.UUID:
    user_id = make_user(engine, "ada@verkies.test", ["admin"], name="Ada Admin")
    api.login("ada@verkies.test")
    api.http.app.dependency_overrides[get_document_storage] = lambda: LocalStorage(tmp_path)  # type: ignore[attr-defined]
    return user_id


def upload(api: ApiClient, account_id: str, name: str, data: bytes, **params: str):  # type: ignore[no-untyped-def]
    return api.send(
        "POST",
        f"/accounts/{account_id}/documents",
        params={"filename": name, **params},
        content=data,
        headers={"Content-Type": "application/octet-stream"},
    )


def test_upload_list_download_and_delete(
    engine: Engine, api: ApiClient, admin: uuid.UUID, tmp_path: Path
) -> None:
    deal = won_deal(engine, api, admin)
    project_id = api.send(
        "POST", f"/deals/{deal['id']}/convert", json={"project": {"name": "Portal"}}
    ).json()["project_id"]
    acme = deal["account_id"]

    made = upload(
        api,
        acme,
        "Signed SOW.pdf",
        PDF,
        kind="sow",
        title="Statement of work",
        project_id=project_id,
    )
    assert made.status_code == 201, made.text
    doc = made.json()
    assert doc["kind_label"] == "Statement of work" and doc["title"] == "Statement of work"
    assert doc["content_type"] == "application/pdf" and doc["size_bytes"] == len(PDF)
    assert doc["project_id"] == project_id and doc["uploaded_by"] == "Ada Admin"

    listed = api.get("/documents", params={"project_id": project_id}).json()
    assert [d["id"] for d in listed] == [doc["id"]]
    assert listed[0]["account_name"] == "Acme Legal"
    assert [d["id"] for d in api.get("/documents", params={"account_id": acme}).json()] == [
        doc["id"]
    ]

    got = api.get(f"/documents/{doc['id']}/download")
    assert got.status_code == 200 and got.content == PDF
    assert got.headers["content-type"] == "application/pdf"
    assert got.headers["content-disposition"].startswith('attachment; filename="Signed SOW.pdf"')
    assert got.headers["x-content-type-options"] == "nosniff"
    assert "sandbox" in got.headers["content-security-policy"]

    renamed = api.send(
        "PATCH", f"/documents/{doc['id']}", json={"title": "SOW v2", "kind": "contract"}
    )
    assert renamed.json()["title"] == "SOW v2" and renamed.json()["kind"] == "contract"

    events = [e["summary"] for e in api.get(f"/accounts/{acme}/timeline").json()]
    assert any(e.startswith("Statement of work added: Statement of work") for e in events)
    actions = {e["action"] for e in api.get(f"/accounts/{acme}/audit").json()}
    assert {"document.uploaded", "document.updated"} <= actions

    # A file changed on disk is never served.
    stored = next(p for p in tmp_path.rglob("*") if p.is_file())
    stored.write_bytes(b"%PDF-1.7 tampered")
    tampered = api.get(f"/documents/{doc['id']}/download")
    assert tampered.status_code == 404 and tampered.json()["error"]["code"] == "file_changed"

    assert api.send("DELETE", f"/documents/{doc['id']}").status_code == 204
    assert api.get("/documents", params={"account_id": acme}).json() == []
    assert api.get(f"/documents/{doc['id']}/download").status_code == 404


def test_what_is_refused(engine: Engine, api: ApiClient, admin: uuid.UUID) -> None:
    acme = str(account(engine, "Acme Legal", domain="acme.test", owner=admin))
    other = won_deal(engine, api, admin, "Other Co")

    html = upload(api, acme, "invoice.html", b"<script>alert(1)</script>")
    assert html.status_code == 422 and html.json()["error"]["code"] == "unsupported_file"
    lying = upload(api, acme, "invoice.pdf", b"<script>alert(1)</script>")
    assert lying.status_code == 422
    empty = upload(api, acme, "empty.pdf", b"")
    assert empty.status_code == 422 and empty.json()["error"]["code"] == "empty_file"
    elsewhere = upload(api, acme, "x.pdf", PDF, deal_id=other["id"])
    assert elsewhere.status_code == 422  # that deal is on another account

    small = Settings(document_max_bytes=2048)
    api.http.app.dependency_overrides[get_settings] = lambda: small  # type: ignore[attr-defined]
    big = upload(api, acme, "big.pdf", PDF + b"0" * 4096)
    assert big.status_code == 422 and big.json()["error"]["code"] == "file_too_large"


def test_documents_follow_the_account(
    engine: Engine,
    api: ApiClient,
    admin: uuid.UUID,
    make_api: Callable[[], ApiClient],
    tmp_path: Path,
) -> None:
    acme = str(account(engine, "Acme Legal", domain="acme.test", owner=admin))
    doc = upload(api, acme, "brief.md", b"# Brief\n", kind="brief").json()

    make_user(engine, "sam@verkies.test", ["salesperson"], name="Sam Seller")
    seller = make_api()
    seller.login("sam@verkies.test")
    seller.http.app.dependency_overrides[get_document_storage] = lambda: LocalStorage(tmp_path)  # type: ignore[attr-defined]
    assert seller.get("/documents").json() == []
    assert seller.get(f"/documents/{doc['id']}/download").status_code == 404
    assert upload(seller, acme, "x.pdf", PDF).status_code == 404

    keep = account(engine, "Acme Legal Ltd", domain="acmelegal.test", owner=admin)
    merged = api.send(
        "POST", f"/accounts/{keep}/merge", json={"merge_id": acme, "reason": "Same firm"}
    )
    assert merged.status_code == 200, merged.text
    assert merged.json()["moved"]["documents"] == 1
    with engine.connect() as conn:
        owner = conn.execute(
            text("SELECT account_id FROM documents WHERE id = :d"), {"d": doc["id"]}
        ).scalar_one()
    assert str(owner) == str(keep)
