"""Backup status (slice 7.2): the latest run and the latest success of each backup step."""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.system.models import BACKUP_KINDS, BackupRun

LABELS = {
    "dump": "Database dump",
    "documents": "Uploaded documents",
    "offsite": "Off-site copy",
    "drill": "Restore test",
}


@dataclass
class BackupStatus:
    kind: str
    latest: BackupRun | None
    last_ok: BackupRun | None


async def status(db: AsyncSession) -> list[BackupStatus]:
    out: list[BackupStatus] = []
    for kind in BACKUP_KINDS:
        base = select(BackupRun).where(BackupRun.kind == kind)
        latest = (
            await db.execute(base.order_by(BackupRun.finished_at.desc()).limit(1))
        ).scalar_one_or_none()
        last_ok = (
            await db.execute(
                base.where(BackupRun.status == "ok").order_by(BackupRun.finished_at.desc()).limit(1)
            )
        ).scalar_one_or_none()
        out.append(BackupStatus(kind, latest, last_ok))
    return out
