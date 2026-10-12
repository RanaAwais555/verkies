"""Uploading, listing, renaming, deleting and downloading documents (master context §14; slice 4.4).

A document belongs to an account and is visible to whoever can see that account. Files are kept in
the documents/ folder of storage under the SHA-256 of their bytes; the hash is checked again on
every download, so a file changed on disk is never served.
"""

import hashlib
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounts import access
from app.accounts.models import Account
from app.audit import service as audit
from app.auth.models import User
from app.clients.models import Project
from app.config import Settings
from app.core.enums import AuditSource, DocumentKind
from app.core.errors import NotFound, ValidationFailed
from app.crm import timeline
from app.crm.models import Opportunity
from app.deals.models import Deal
from app.documents.files import clean_filename, detect
from app.documents.models import Document
from app.providers.storage import LocalStorage, Storage

KIND_LABELS = {
    DocumentKind.PROPOSAL: "Proposal",
    DocumentKind.REQUIREMENTS: "Requirements",
    DocumentKind.BRIEF: "Brief",
    DocumentKind.CONTRACT: "Contract",
    DocumentKind.SOW: "Statement of work",
    DocumentKind.MEETING_NOTES: "Meeting notes",
    DocumentKind.SCREENSHOT: "Screenshot",
    DocumentKind.PROJECT_DOCUMENT: "Project document",
    DocumentKind.OTHER: "Other",
}


def document_storage(settings: Settings) -> Storage:
    return LocalStorage(Path(settings.storage_dir) / "documents")


def _plain(value: Any) -> Any:
    if isinstance(value, DocumentKind):
        return value.value
    return str(value) if isinstance(value, uuid.UUID) else value


def _size(n: int) -> str:
    if n < 1024:
        return f"{n} bytes"
    if n < 1024 * 1024:
        return f"{n / 1024:.0f} KB"
    return f"{n / 1024 / 1024:.1f} MB"


async def _account(db: AsyncSession, user: User, account_id: uuid.UUID) -> Account:
    account = await db.get(Account, account_id)
    if (
        account is None
        or account.deleted_at is not None
        or not access.can_see(user, account.owner_id)
    ):
        raise NotFound("Account not found.")
    return account


async def _check_links(
    db: AsyncSession,
    account: Account,
    *,
    opportunity_id: uuid.UUID | None,
    deal_id: uuid.UUID | None,
    project_id: uuid.UUID | None,
) -> None:
    for model, record_id, what in (
        (Opportunity, opportunity_id, "opportunity"),
        (Deal, deal_id, "deal"),
        (Project, project_id, "project"),
    ):
        if record_id is None:
            continue
        found: Any = await db.get(model, record_id)
        if found is None or found.deleted_at is not None or found.account_id != account.id:
            raise ValidationFailed(f"That {what} is not on this account.")


@dataclass
class Upload:
    filename: str
    data: bytes
    kind: DocumentKind = DocumentKind.OTHER
    title: str | None = None
    opportunity_id: uuid.UUID | None = None
    deal_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None


async def upload(
    db: AsyncSession,
    *,
    user: User,
    account_id: uuid.UUID,
    file: Upload,
    storage: Storage,
    settings: Settings,
) -> Document:
    account = await _account(db, user, account_id)
    if not file.data:
        raise ValidationFailed("The file is empty.", code="empty_file")
    if len(file.data) > settings.document_max_bytes:
        raise ValidationFailed(
            f"Files can be up to {_size(settings.document_max_bytes)}.", code="file_too_large"
        )
    filename = clean_filename(file.filename)
    content_type = detect(file.data, filename)
    await _check_links(
        db,
        account,
        opportunity_id=file.opportunity_id,
        deal_id=file.deal_id,
        project_id=file.project_id,
    )
    key = storage.put(file.data)
    document = Document(
        account_id=account.id,
        opportunity_id=file.opportunity_id,
        deal_id=file.deal_id,
        project_id=file.project_id,
        kind=file.kind,
        title=(file.title or "").strip()[:200] or filename,
        filename=filename,
        content_type=content_type,
        size_bytes=len(file.data),
        storage_key=key,
        uploaded_by_id=user.id,
    )
    db.add(document)
    await db.flush()
    timeline.add(
        db,
        account_id=account.id,
        event_type="document.uploaded",
        summary=f"{KIND_LABELS[document.kind]} added: {document.title} ({_size(len(file.data))}).",
        actor_id=user.id,
        ref_table="documents",
        ref_id=document.id,
    )
    audit.record(
        db,
        action="document.uploaded",
        object_table="documents",
        object_id=document.id,
        user_id=user.id,
        source=AuditSource.API,
        new_value={
            "account_id": str(account.id),
            "kind": document.kind.value,
            "filename": filename,
            "content_type": content_type,
            "size_bytes": document.size_bytes,
            "sha256": key,
            "deal_id": str(file.deal_id) if file.deal_id else None,
            "project_id": str(file.project_id) if file.project_id else None,
            "opportunity_id": str(file.opportunity_id) if file.opportunity_id else None,
        },
    )
    await db.commit()
    return document


async def get_document(db: AsyncSession, *, user: User, document_id: uuid.UUID) -> Document:
    document = await db.get(Document, document_id)
    if document is None or document.deleted_at is not None:
        raise NotFound("Document not found.")
    await _account(db, user, document.account_id)
    return document


async def list_documents(
    db: AsyncSession,
    *,
    user: User,
    account_id: uuid.UUID | None = None,
    deal_id: uuid.UUID | None = None,
    project_id: uuid.UUID | None = None,
    kind: DocumentKind | None = None,
    limit: int = 200,
) -> list[tuple[Document, Account, str | None]]:
    stmt = (
        select(Document, Account, User.name)
        .join(Account, Account.id == Document.account_id)
        .outerjoin(User, User.id == Document.uploaded_by_id)
        .where(Document.deleted_at.is_(None), Account.deleted_at.is_(None))
    )
    clause = access.visible(user)
    if clause is not None:
        stmt = stmt.where(clause)
    if account_id is not None:
        stmt = stmt.where(Document.account_id == account_id)
    if deal_id is not None:
        stmt = stmt.where(Document.deal_id == deal_id)
    if project_id is not None:
        stmt = stmt.where(Document.project_id == project_id)
    if kind is not None:
        stmt = stmt.where(Document.kind == kind)
    stmt = stmt.order_by(Document.created_at.desc(), Document.id).limit(limit)
    return [(d, a, n) for d, a, n in (await db.execute(stmt)).all()]


EDITABLE = ("title", "kind", "opportunity_id", "deal_id", "project_id")


async def update_document(
    db: AsyncSession, *, user: User, document_id: uuid.UUID, changes: dict[str, Any]
) -> None:
    document = await get_document(db, user=user, document_id=document_id)
    account = await _account(db, user, document.account_id)
    if "title" in changes:
        changes["title"] = (changes["title"] or "").strip()[:200]
        if not changes["title"]:
            raise ValidationFailed("A document needs a title.")
    await _check_links(
        db,
        account,
        opportunity_id=changes.get("opportunity_id"),
        deal_id=changes.get("deal_id"),
        project_id=changes.get("project_id"),
    )
    changed = {k: v for k, v in changes.items() if k in EDITABLE and getattr(document, k) != v}
    if not changed:
        return
    old = {k: _plain(getattr(document, k)) for k in changed}
    for key, value in changed.items():
        setattr(document, key, value)
    audit.record(
        db,
        action="document.updated",
        object_table="documents",
        object_id=document.id,
        user_id=user.id,
        source=AuditSource.API,
        old_value=old,
        new_value={k: _plain(v) for k, v in changed.items()},
    )
    await db.commit()


async def delete_document(db: AsyncSession, *, user: User, document_id: uuid.UUID) -> None:
    """Removed from VROS. The file stays in storage (other uploads may share its bytes) and is
    kept with the backups."""
    document = await get_document(db, user=user, document_id=document_id)
    document.deleted_at = datetime.now(UTC)
    timeline.add(
        db,
        account_id=document.account_id,
        event_type="document.deleted",
        summary=f"Document removed: {document.title}.",
        actor_id=user.id,
        ref_table="documents",
        ref_id=document.id,
    )
    audit.record(
        db,
        action="document.deleted",
        object_table="documents",
        object_id=document.id,
        user_id=user.id,
        source=AuditSource.API,
        old_value={"title": document.title, "filename": document.filename},
    )
    await db.commit()


def read(document: Document, storage: Storage) -> bytes:
    """The file's bytes, checked against the hash recorded at upload."""
    try:
        data = storage.get(document.storage_key)
    except (FileNotFoundError, ValueError) as exc:
        raise NotFound("The file is missing from storage.", code="file_missing") from exc
    if hashlib.sha256(data).hexdigest() != document.storage_key:
        raise NotFound("The stored file no longer matches what was uploaded.", code="file_changed")
    return data
