"""/users and /roles: team administration. Requires the users.manage permission."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.auth import service
from app.auth.deps import AppSettings, DbSession, require_permission
from app.auth.models import User
from app.auth.schemas import InviteCreate, InviteCreated, InviteOut, RoleOut, UserOut, UserUpdate

Admin = Annotated[User, Depends(require_permission("users.manage"))]

router = APIRouter(tags=["users"])


@router.get("/roles")
async def list_roles(_: Admin, db: DbSession) -> list[RoleOut]:
    return [RoleOut.of(r) for r in await service.list_roles(db)]


@router.get("/users")
async def list_users(_: Admin, db: DbSession) -> list[UserOut]:
    return [UserOut.of(u) for u in await service.list_users(db)]


@router.patch("/users/{user_id}")
async def update_user(
    user_id: uuid.UUID, body: UserUpdate, actor: Admin, db: DbSession, settings: AppSettings
) -> UserOut:
    user = await service.update_user(
        db,
        actor=actor,
        user_id=user_id,
        role_keys=body.roles,
        is_active=body.is_active,
        settings=settings,
    )
    await db.commit()
    return UserOut.of(user)


@router.get("/users/invites")
async def list_invites(_: Admin, db: DbSession) -> list[InviteOut]:
    return [InviteOut.of(i) for i in await service.list_pending_invites(db)]


@router.post("/users/invites", status_code=status.HTTP_201_CREATED)
async def create_invite(
    body: InviteCreate, actor: Admin, db: DbSession, settings: AppSettings
) -> InviteCreated:
    issued = await service.create_invite(
        db, actor=actor, email=body.email, role_keys=body.roles, settings=settings
    )
    await db.commit()
    await db.refresh(issued.invite, ["created_at"])
    return InviteCreated(
        **InviteOut.of(issued.invite).model_dump(),
        invite_url=f"{settings.public_url}/invite#token={issued.token}",
    )


@router.delete("/users/invites/{invite_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_invite(invite_id: uuid.UUID, actor: Admin, db: DbSession) -> None:
    await service.revoke_invite(db, actor=actor, invite_id=invite_id)
    await db.commit()
