"""/documents: upload (the file is the request body), list, rename, delete and download
(slice 4.4)."""

import uuid
from datetime import datetime
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel, Field

from app.auth.deps import AppSettings, DbSession, require_permission
from app.auth.models import User
from app.config import Settings, get_settings
from app.core.enums import DocumentKind
from app.core.errors import ValidationFailed
from app.documents import service
from app.documents.models import Document
from app.providers.storage import Storage

router = APIRouter(tags=["documents"])

Member = Annotated[User, Depends(require_permission("accounts.read", "accounts.read_own"))]


def get_document_storage(settings: Annotated[Settings, Depends(get_settings)]) -> Storage:
    return service.document_storage(settings)


DocumentStorage = Annotated[Storage, Depends(get_document_storage)]


class DocumentOut(BaseModel):
    id: uuid.UUID
    account_id: uuid.UUID
    account_name: str | None
    opportunity_id: uuid.UUID | None
    deal_id: uuid.UUID | None
    project_id: uuid.UUID | None
    kind: str
    kind_label: str
    title: str
    filename: str
    content_type: str
    size_bytes: int
    uploaded_by: str | None
    created_at: datetime

    @classmethod
    def of(cls, d: Document, account_name: str | None, uploaded_by: str | None) -> "DocumentOut":
        return cls(
            id=d.id,
            account_id=d.account_id,
            account_name=account_name,
            opportunity_id=d.opportunity_id,
            deal_id=d.deal_id,
            project_id=d.project_id,
            kind=d.kind.value,
            kind_label=service.KIND_LABELS[d.kind],
            title=d.title,
            filename=d.filename,
            content_type=d.content_type,
            size_bytes=d.size_bytes,
            uploaded_by=uploaded_by,
            created_at=d.created_at,
        )


class UpdateDocument(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    kind: DocumentKind | None = None
    opportunity_id: uuid.UUID | None = None
    deal_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None


async def _body(request: Request, limit: int) -> bytes:
    """The request body, refused as soon as it passes the limit rather than read in full."""
    declared = request.headers.get("content-length")
    too_large = ValidationFailed(
        f"Files can be up to {limit // (1024 * 1024)} MB.", code="file_too_large"
    )
    if declared is not None and declared.isdigit() and int(declared) > limit:
        raise too_large
    chunks: list[bytes] = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > limit:
            raise too_large
        chunks.append(chunk)
    return b"".join(chunks)


@router.post("/accounts/{account_id}/documents", status_code=201)
async def upload_document(
    account_id: uuid.UUID,
    request: Request,
    user: Member,
    db: DbSession,
    settings: AppSettings,
    storage: DocumentStorage,
    filename: Annotated[str, Query(min_length=1, max_length=255)],
    kind: DocumentKind = DocumentKind.OTHER,
    title: Annotated[str | None, Query(max_length=200)] = None,
    opportunity_id: uuid.UUID | None = None,
    deal_id: uuid.UUID | None = None,
    project_id: uuid.UUID | None = None,
) -> DocumentOut:
    data = await _body(request, settings.document_max_bytes)
    document = await service.upload(
        db,
        user=user,
        account_id=account_id,
        file=service.Upload(
            filename=filename,
            data=data,
            kind=kind,
            title=title,
            opportunity_id=opportunity_id,
            deal_id=deal_id,
            project_id=project_id,
        ),
        storage=storage,
        settings=settings,
    )
    return DocumentOut.of(document, None, user.name)


@router.get("/documents")
async def list_documents(
    user: Member,
    db: DbSession,
    account_id: uuid.UUID | None = None,
    deal_id: uuid.UUID | None = None,
    project_id: uuid.UUID | None = None,
    kind: DocumentKind | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
) -> list[DocumentOut]:
    rows = await service.list_documents(
        db,
        user=user,
        account_id=account_id,
        deal_id=deal_id,
        project_id=project_id,
        kind=kind,
        limit=limit,
    )
    return [DocumentOut.of(d, a.name, n) for d, a, n in rows]


@router.patch("/documents/{document_id}")
async def update_document(
    document_id: uuid.UUID, body: UpdateDocument, user: Member, db: DbSession
) -> DocumentOut:
    changes = body.model_dump(exclude_unset=True)
    if "kind" in changes and changes["kind"] is None:
        raise ValidationFailed("A document needs a kind.")
    if not changes:
        raise ValidationFailed("Nothing to change.")
    await service.update_document(db, user=user, document_id=document_id, changes=changes)
    document = await service.get_document(db, user=user, document_id=document_id)
    return DocumentOut.of(document, None, None)


@router.delete("/documents/{document_id}", status_code=204)
async def delete_document(document_id: uuid.UUID, user: Member, db: DbSession) -> Response:
    await service.delete_document(db, user=user, document_id=document_id)
    return Response(status_code=204)


@router.get("/documents/{document_id}/download")
async def download_document(
    document_id: uuid.UUID, user: Member, db: DbSession, storage: DocumentStorage
) -> Response:
    """Always an attachment, never shown in the page, with the type decided at upload."""
    document = await service.get_document(db, user=user, document_id=document_id)
    data = service.read(document, storage)
    ascii_name = document.filename.encode("ascii", "replace").decode().replace('"', "'")
    return Response(
        data,
        media_type=document.content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{ascii_name}"; '
            f"filename*=UTF-8''{quote(document.filename)}",
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'; sandbox",
            "Cache-Control": "private, no-store",
        },
    )
