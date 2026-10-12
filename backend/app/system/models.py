"""What the backup service did (slice 7.2)."""

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base

BACKUP_KINDS = ("dump", "documents", "offsite", "drill")
BACKUP_STATUSES = ("ok", "failed", "skipped")


class BackupRun(Base):
    """One step of a backup cycle, written by ops/backup/backup.sh with psql (hence the
    database-side id): the dump, the documents archive, the off-site copy or the restore drill."""

    __tablename__ = "backup_runs"
    __table_args__ = (
        CheckConstraint(f"kind IN {BACKUP_KINDS}", name="kind"),
        CheckConstraint(f"status IN {BACKUP_STATUSES}", name="status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    kind: Mapped[str] = mapped_column(String(20), index=True)
    status: Mapped[str] = mapped_column(String(20))
    started_at: Mapped[datetime]
    finished_at: Mapped[datetime] = mapped_column(server_default=func.now())
    bytes: Mapped[int | None] = mapped_column(BigInteger)
    detail: Mapped[str | None] = mapped_column(Text)
