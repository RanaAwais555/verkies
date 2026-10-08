"""Request and response models for auth and user administration."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.auth.models import Invite, Role, User


class LoginRequest(BaseModel):
    email: str = Field(max_length=320)
    password: str = Field(max_length=256)


class RoleOut(BaseModel):
    key: str
    name: str
    permissions: list[str]

    @classmethod
    def of(cls, role: Role) -> "RoleOut":
        return cls(key=role.key, name=role.name, permissions=[p.key for p in role.permissions])


class UserOut(BaseModel):
    id: uuid.UUID
    email: str
    name: str
    roles: list[str]
    permissions: list[str]
    is_active: bool
    last_login_at: datetime | None

    @classmethod
    def of(cls, user: User) -> "UserOut":
        return cls(
            id=user.id,
            email=user.email,
            name=user.name,
            roles=[r.key for r in user.roles],
            permissions=sorted(user.permission_keys),
            is_active=user.is_active,
            last_login_at=user.last_login_at,
        )


class SessionOut(BaseModel):
    user: UserOut
    # The frontend sends this back in the X-CSRF-Token header on state-changing requests.
    csrf_token: str


class PasswordChange(BaseModel):
    current_password: str = Field(max_length=256)
    new_password: str = Field(max_length=256)


class InviteCreate(BaseModel):
    email: str = Field(max_length=320)
    roles: list[str] = Field(min_length=1)


class InviteOut(BaseModel):
    id: uuid.UUID
    email: str
    roles: list[str]
    expires_at: datetime
    created_at: datetime

    @classmethod
    def of(cls, invite: Invite) -> "InviteOut":
        return cls(
            id=invite.id,
            email=invite.email,
            roles=sorted(r.key for r in invite.roles),
            expires_at=invite.expires_at,
            created_at=invite.created_at,
        )


class InviteCreated(InviteOut):
    # Shown once. The token is in the URL fragment, which browsers never send to servers.
    invite_url: str


class InviteToken(BaseModel):
    token: str = Field(max_length=200)


class InviteInfo(BaseModel):
    email: str
    roles: list[str]
    expires_at: datetime


class InviteAccept(BaseModel):
    token: str = Field(max_length=200)
    name: str = Field(min_length=1, max_length=120)
    password: str = Field(max_length=256)


class UserUpdate(BaseModel):
    roles: list[str] | None = None
    is_active: bool | None = None
