"""Saving a new version of the ICP or scoring configuration: validated, activated, audited.

Used by the config editor (PUT /config/{kind}) and by activating a learned proposal (slice 5.3),
so both go through exactly the same checks.
"""

from typing import Any

from pydantic import BaseModel, ValidationError
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import service as audit
from app.auth.models import User
from app.core.enums import AuditSource
from app.core.errors import ValidationFailed as InvalidConfig
from app.qualification.config import IcpConfigModel
from app.qualification.models import IcpConfig
from app.scoring.config import ScoringConfigModel
from app.scoring.models import ScoringConfig

TABLES: dict[str, Any] = {"icp": IcpConfig, "scoring": ScoringConfig}
MODELS: dict[str, type[BaseModel]] = {"icp": IcpConfigModel, "scoring": ScoringConfigModel}


async def active_version(db: AsyncSession, kind: str) -> Any:
    table = TABLES[kind]
    return (await db.execute(select(table).where(table.is_active.is_(True)))).scalar_one_or_none()


async def save_version(
    db: AsyncSession,
    *,
    kind: str,
    config: dict[str, Any],
    note: str | None,
    actor: User,
    reason: str | None = None,
) -> Any:
    """Validate, deactivate the current version and activate the new one. The caller commits."""
    try:
        validated = MODELS[kind].model_validate(config)
    except ValidationError as exc:
        problems = "; ".join(
            f"{'.'.join(map(str, e['loc'])) or kind}: {e['msg']}" for e in exc.errors()
        )
        raise InvalidConfig(f"Invalid {kind} configuration: {problems}") from None
    table = TABLES[kind]
    previous = await active_version(db, kind)
    latest = (await db.execute(select(func.max(table.version)))).scalar_one() or 0
    await db.execute(update(table).where(table.is_active.is_(True)).values(is_active=False))
    await db.flush()
    row = table(
        version=latest + 1,
        is_active=True,
        config=validated.model_dump(),
        note=note,
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
        reason=reason or note,
    )
    return row
