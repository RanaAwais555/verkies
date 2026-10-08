"""/config: view and version the ICP and scoring configuration (admins edit; everyone reads).

Every change creates a new version and activates it; old versions stay, and every
qualification result and score snapshot records which version produced it.
"""

from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ValidationError
from sqlalchemy import func, select, update

from app.audit import service as audit
from app.auth.deps import DbSession, require_permission
from app.auth.models import User
from app.core.enums import AuditSource
from app.core.errors import NotFound
from app.core.errors import ValidationFailed as InvalidConfig
from app.qualification.config import IcpConfigModel
from app.qualification.models import IcpConfig
from app.scoring.config import ScoringConfigModel
from app.scoring.models import ScoringConfig

router = APIRouter(prefix="/config", tags=["config"])

Reader = Annotated[
    User,
    Depends(
        require_permission("research.run", "accounts.read", "accounts.read_own", "config.manage")
    ),
]
Admin = Annotated[User, Depends(require_permission("config.manage"))]

Kind = Literal["icp", "scoring"]
TABLES: dict[str, Any] = {"icp": IcpConfig, "scoring": ScoringConfig}
MODELS: dict[str, type[BaseModel]] = {"icp": IcpConfigModel, "scoring": ScoringConfigModel}


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
    try:
        validated = MODELS[kind].model_validate(body.config)
    except ValidationError as exc:
        problems = "; ".join(
            f"{'.'.join(map(str, e['loc'])) or kind}: {e['msg']}" for e in exc.errors()
        )
        raise InvalidConfig(f"Invalid {kind} configuration: {problems}") from None
    table = TABLES[kind]
    previous = (
        await db.execute(select(table).where(table.is_active.is_(True)))
    ).scalar_one_or_none()
    latest = (await db.execute(select(func.max(table.version)))).scalar_one() or 0
    await db.execute(update(table).where(table.is_active.is_(True)).values(is_active=False))
    await db.flush()
    row = table(
        version=latest + 1,
        is_active=True,
        config=validated.model_dump(),
        note=body.note,
        created_by_id=actor.id,
    )
    db.add(row)
    await db.flush()
    audit.record(
        db,
        action=f"config.{kind}.updated",
        object_table=table.__tablename__,
        object_id=row.id,
        user_id=actor.id,
        source=AuditSource.API,
        old_value={"version": previous.version} if previous else None,
        new_value={"version": row.version},
        reason=body.note,
    )
    await db.commit()
    await db.refresh(row)
    return _out(kind, row)
