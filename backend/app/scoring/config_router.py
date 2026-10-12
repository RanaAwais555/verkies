"""/config: view and version the ICP and scoring configuration (admins edit; everyone reads).

Every change creates a new version and activates it; old versions stay, and every
qualification result and score snapshot records which version produced it.
"""

from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select

from app.auth.deps import DbSession, require_permission
from app.auth.models import User
from app.core.errors import NotFound
from app.scoring.versions import TABLES, save_version

router = APIRouter(prefix="/config", tags=["config"])

Reader = Annotated[
    User,
    Depends(
        require_permission("research.run", "accounts.read", "accounts.read_own", "config.manage")
    ),
]
Admin = Annotated[User, Depends(require_permission("config.manage"))]

Kind = Literal["icp", "scoring"]


class ConfigVersion(BaseModel):
    kind: str
    version: int
    is_active: bool
    note: str | None
    created_at: datetime
    config: dict[str, Any]


class ConfigUpdate(BaseModel):
    config: dict[str, Any]
    note: str | None = None


def _out(kind: str, row: Any) -> ConfigVersion:
    return ConfigVersion(
        kind=kind,
        version=row.version,
        is_active=row.is_active,
        note=row.note,
        created_at=row.created_at,
        config=row.config,
    )


@router.get("/{kind}")
async def active(kind: Kind, _: Reader, db: DbSession) -> ConfigVersion:
    table = TABLES[kind]
    row = (await db.execute(select(table).where(table.is_active.is_(True)))).scalar_one_or_none()
    if row is None:
        raise NotFound(f"No active {kind} configuration.")
    return _out(kind, row)


@router.get("/{kind}/versions")
async def versions(kind: Kind, _: Reader, db: DbSession) -> list[ConfigVersion]:
    table = TABLES[kind]
    rows = (await db.execute(select(table).order_by(table.version.desc()))).scalars()
    return [_out(kind, r) for r in rows]


@router.put("/{kind}")
async def update_config(
    kind: Kind, body: ConfigUpdate, actor: Admin, db: DbSession
) -> ConfigVersion:
    row = await save_version(db, kind=kind, config=body.config, note=body.note, actor=actor)
    await db.commit()
    await db.refresh(row)
    return _out(kind, row)
