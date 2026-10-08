"""Users, roles, permissions, sessions and invites (SECURITY.md §1-2)."""

import uuid
from datetime import datetime

from sqlalchemy import Column, ForeignKey, String, Table, Text
from sqlalchemy.dialects.postgresql import CITEXT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.models import Base, CreatedMixin, IdMixin, TimestampMixin

role_permissions = Table(
    "role_permissions",
    Base.metadata,
    Column("role_id", ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
    Column("permission_id", ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True),
)

user_roles = Table(
    "user_roles",
    Base.metadata,
    Column("user_id", ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("role_id", ForeignKey("roles.id", ondelete="RESTRICT"), primary_key=True),
)

invite_roles = Table(
    "invite_roles",
    Base.metadata,
    Column("invite_id", ForeignKey("invites.id", ondelete="CASCADE"), primary_key=True),
    Column("role_id", ForeignKey("roles.id", ondelete="RESTRICT"), primary_key=True),
)


class Permission(IdMixin, Base):
    __tablename__ = "permissions"

    key: Mapped[str] = mapped_column(String(64), unique=True)
    description: Mapped[str] = mapped_column(Text)


class Role(IdMixin, TimestampMixin, Base):
    __tablename__ = "roles"

    key: Mapped[str] = mapped_column(String(40), unique=True)
    name: Mapped[str] = mapped_column(String(80))
    description: Mapped[str] = mapped_column(Text, default="")
    permissions: Mapped[list[Permission]] = relationship(
        secondary=role_permissions, lazy="selectin", order_by=Permission.key
    )


class User(IdMixin, TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(CITEXT, unique=True)
    name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(default=True)
    last_login_at: Mapped[datetime | None]
    failed_login_count: Mapped[int] = mapped_column(default=0)
    locked_until: Mapped[datetime | None]
    roles: Mapped[list[Role]] = relationship(
        secondary=user_roles, lazy="selectin", order_by=Role.key
    )

    @property
    def permission_keys(self) -> frozenset[str]:
        return frozenset(p.key for role in self.roles for p in role.permissions)


class UserSession(IdMixin, CreatedMixin, Base):
    """Server-side session. The cookie holds a random token; only its keyed hash is stored."""

    __tablename__ = "user_sessions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    last_seen_at: Mapped[datetime]
    expires_at: Mapped[datetime]
    revoked_at: Mapped[datetime | None]
    ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(400))

    user: Mapped[User] = relationship(lazy="joined")


class Invite(IdMixin, TimestampMixin, Base):
    """Single-use, expiring, email-bound invitation. There is no public sign-up."""

    __tablename__ = "invites"

    email: Mapped[str] = mapped_column(CITEXT, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    invited_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    expires_at: Mapped[datetime]
    accepted_at: Mapped[datetime | None]
    accepted_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    revoked_at: Mapped[datetime | None]
    roles: Mapped[list[Role]] = relationship(secondary=invite_roles, lazy="selectin")
