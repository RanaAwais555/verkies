"""Documents (master context §14; slice 4.4): files people upload, each linked to its account and,
when it belongs to one, a deal, opportunity or project."""

import uuid

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import DocumentKind
from app.core.models import Base, IdMixin, SoftDeleteMixin, TimestampMixin, text_enum


class Document(IdMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint("size_bytes > 0", name="size_positive"),
        CheckConstraint("storage_key ~ '^[0-9a-f]{64}$'", name="storage_key_sha256"),
    )

    account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("accounts.id"), index=True)
    opportunity_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("opportunities.id"))
    deal_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("deals.id"), index=True)
    project_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("projects.id"), index=True)
    kind: Mapped[DocumentKind] = mapped_column(text_enum(DocumentKind), default=DocumentKind.OTHER)
    title: Mapped[str] = mapped_column(String(200))
    # The name it was uploaded with, cleaned; used only to name the download.
    filename: Mapped[str] = mapped_column(String(200))
    # Decided from the file's own bytes, never from what the browser said.
    content_type: Mapped[str] = mapped_column(String(120))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    # SHA-256 of the bytes: the key in document storage, and a check against tampering.
    storage_key: Mapped[str] = mapped_column(String(64))
    uploaded_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
