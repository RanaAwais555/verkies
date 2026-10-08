"""Team authentication: login, sessions, invites, passwords and user administration.

Every state change is audited in the same transaction. Callers commit.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.audit import service as audit
from app.auth.models import Invite, Role, User, UserSession, user_roles
from app.auth.passwords import check_password_policy, hash_password, needs_rehash, verify_password
from app.auth.tokens import hash_token, new_token
from app.config import Settings
from app.core.enums import AuditSource
from app.core.errors import Conflict, NotAuthenticated, NotFound, ValidationFailed

ADMIN_ROLE = "admin"
# Updating last_seen_at on every request would write on every call; this is precise enough.
LAST_SEEN_RESOLUTION = timedelta(minutes=5)
INVALID_LOGIN = "Invalid email or password."


def _now() -> datetime:
    return datetime.now(UTC)


def normalise_email(email: str) -> str:
    email = email.strip()
    if "@" not in email or len(email) > 320 or any(c.isspace() for c in email):
        raise ValidationFailed("Enter a valid email address.")
    return email


@dataclass(frozen=True)
class IssuedSession:
    token: str
    session: UserSession


# --- users and roles ----------------------------------------------------------------------


async def get_user(db: AsyncSession, user_id: uuid.UUID) -> User:
    user = await db.get(
        User, user_id, options=[selectinload(User.roles).selectinload(Role.permissions)]
    )
    if user is None:
        raise NotFound("User not found.")
    return user


async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
    result = await db.execute(
        select(User)
        .where(User.email == email)
        .options(selectinload(User.roles).selectinload(Role.permissions))
    )
    return result.scalar_one_or_none()


async def list_users(db: AsyncSession) -> list[User]:
    result = await db.execute(
        select(User)
        .order_by(User.name)
        .options(selectinload(User.roles).selectinload(Role.permissions))
    )
    return list(result.scalars())


async def list_roles(db: AsyncSession) -> list[Role]:
    result = await db.execute(
        select(Role).order_by(Role.key).options(selectinload(Role.permissions))
    )
    return list(result.scalars())


async def roles_by_key(db: AsyncSession, keys: list[str]) -> list[Role]:
    wanted = set(keys)
    if not wanted:
        raise ValidationFailed("Choose at least one role.")
    result = await db.execute(
        select(Role).where(Role.key.in_(wanted)).options(selectinload(Role.permissions))
    )
    roles = list(result.scalars())
    unknown = wanted - {r.key for r in roles}
    if unknown:
        raise ValidationFailed(f"Unknown role(s): {', '.join(sorted(unknown))}.")
    return roles


async def _active_admin_count(db: AsyncSession, *, excluding: uuid.UUID | None = None) -> int:
    query = (
        select(func.count(func.distinct(User.id)))
        .join(user_roles, user_roles.c.user_id == User.id)
        .join(Role, Role.id == user_roles.c.role_id)
        .where(Role.key == ADMIN_ROLE, User.is_active.is_(True))
    )
    if excluding is not None:
        query = query.where(User.id != excluding)
    return (await db.execute(query)).scalar_one()


async def create_admin(db: AsyncSession, *, email: str, name: str, password: str) -> User:
    """Bootstrap path used by the CLI on the server. There is no public sign-up."""
    email = normalise_email(email)
    if await get_user_by_email(db, email) is not None:
        raise Conflict("A user with this email already exists.")
    check_password_policy(password, email=email)
    user = User(email=email, name=name.strip(), password_hash=hash_password(password))
    user.roles = await roles_by_key(db, [ADMIN_ROLE])
    db.add(user)
    await db.flush()
    audit.record(
        db,
        action="user.created",
        object_table="users",
        object_id=user.id,
        user_id=None,
        source=AuditSource.CLI,
        new_value={"email": email, "roles": [ADMIN_ROLE]},
        reason="bootstrap admin",
    )
    return user


async def update_user(
    db: AsyncSession,
    *,
    actor: User,
    user_id: uuid.UUID,
    role_keys: list[str] | None,
    is_active: bool | None,
    settings: Settings,
) -> User:
    user = await get_user(db, user_id)
    old = {"roles": [r.key for r in user.roles], "is_active": user.is_active}
    loses_admin = (role_keys is not None and ADMIN_ROLE not in role_keys) or is_active is False
    is_admin = any(r.key == ADMIN_ROLE for r in user.roles) and user.is_active
    if is_admin and loses_admin and await _active_admin_count(db, excluding=user.id) == 0:
        raise Conflict("VROS must keep at least one active admin.")
    if role_keys is not None:
        user.roles = await roles_by_key(db, role_keys)
    if is_active is not None:
        user.is_active = is_active
        if not is_active:
            await revoke_all_sessions(db, user.id)
    new = {"roles": [r.key for r in user.roles], "is_active": user.is_active}
    if new != old:
        audit.record(
            db,
            action="user.updated",
            object_table="users",
            object_id=user.id,
            user_id=actor.id,
            source=AuditSource.API,
            old_value=old,
            new_value=new,
        )
    return user


# --- login and sessions -------------------------------------------------------------------


async def authenticate(db: AsyncSession, *, email: str, password: str, settings: Settings) -> User:
    """Return the user or raise one generic error, whatever the reason (unknown email, wrong
    password, locked, deactivated), so the response never reveals which accounts exist."""
    now = _now()
    user = await get_user_by_email(db, email.strip())
    password_ok = verify_password(user.password_hash if user else None, password)
    if user is None:
        raise NotAuthenticated(INVALID_LOGIN)

    if user.locked_until is not None and user.locked_until > now:
        audit.record(
            db,
            action="auth.login_failed",
            object_table="users",
            object_id=user.id,
            user_id=None,
            source=AuditSource.API,
            reason="account locked",
        )
        raise NotAuthenticated(INVALID_LOGIN)

    if not password_ok or not user.is_active:
        if not password_ok:
            user.failed_login_count += 1
            if user.failed_login_count >= settings.login_max_failures:
                user.locked_until = now + timedelta(minutes=settings.login_lockout_minutes)
                user.failed_login_count = 0
        audit.record(
            db,
            action="auth.login_failed",
            object_table="users",
            object_id=user.id,
            user_id=None,
            source=AuditSource.API,
            reason="inactive user" if password_ok else "wrong password",
        )
        raise NotAuthenticated(INVALID_LOGIN)

    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = now
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
    audit.record(
        db,
        action="auth.login",
        object_table="users",
        object_id=user.id,
        user_id=user.id,
        source=AuditSource.API,
    )
    return user


def issue_session(
    db: AsyncSession, user: User, *, settings: Settings, ip: str | None, user_agent: str | None
) -> IssuedSession:
    token = new_token()
    now = _now()
    session = UserSession(
        user_id=user.id,
        token_hash=hash_token(token, settings.signing_key),
        last_seen_at=now,
        expires_at=now + timedelta(days=settings.session_max_days),
        ip=ip,
        user_agent=(user_agent or "")[:400] or None,
    )
    session.user = user
    db.add(session)
    return IssuedSession(token=token, session=session)


async def resolve_session(
    db: AsyncSession, token: str, *, settings: Settings
) -> UserSession | None:
    """The live session for a cookie token, or None if missing, revoked, expired or idle."""
    now = _now()
    result = await db.execute(
        select(UserSession)
        .where(UserSession.token_hash == hash_token(token, settings.signing_key))
        .options(
            selectinload(UserSession.user).selectinload(User.roles).selectinload(Role.permissions)
        )
    )
    session = result.scalar_one_or_none()
    if session is None or session.revoked_at is not None or session.expires_at <= now:
        return None
    if session.last_seen_at + timedelta(minutes=settings.session_idle_minutes) <= now:
        return None
    if not session.user.is_active:
        return None
    if now - session.last_seen_at >= LAST_SEEN_RESOLUTION:
        session.last_seen_at = now
        await db.commit()  # persist activity now, whatever the endpoint does next
    return session


async def revoke_session(db: AsyncSession, session: UserSession) -> None:
    session.revoked_at = _now()


async def revoke_all_sessions(
    db: AsyncSession, user_id: uuid.UUID, *, except_session_id: uuid.UUID | None = None
) -> None:
    query = (
        update(UserSession)
        .where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
        .values(revoked_at=_now())
    )
    if except_session_id is not None:
        query = query.where(UserSession.id != except_session_id)
    await db.execute(query)


async def change_password(
    db: AsyncSession, *, user: User, current_session: UserSession, current: str, new: str
) -> None:
    if not verify_password(user.password_hash, current):
        raise ValidationFailed("Current password is incorrect.")
    check_password_policy(new, email=user.email)
    user.password_hash = hash_password(new)
    # Anyone else holding a session for this account is signed out.
    await revoke_all_sessions(db, user.id, except_session_id=current_session.id)
    audit.record(
        db,
        action="auth.password_changed",
        object_table="users",
        object_id=user.id,
        user_id=user.id,
        source=AuditSource.API,
    )


# --- invites ------------------------------------------------------------------------------


@dataclass(frozen=True)
class IssuedInvite:
    token: str
    invite: Invite


async def create_invite(
    db: AsyncSession, *, actor: User, email: str, role_keys: list[str], settings: Settings
) -> IssuedInvite:
    email = normalise_email(email)
    if await get_user_by_email(db, email) is not None:
        raise Conflict("This person already has an account.")
    roles = await roles_by_key(db, role_keys)
    now = _now()
    # A new invite replaces any pending one for the same address.
    await db.execute(
        update(Invite)
        .where(Invite.email == email, Invite.accepted_at.is_(None), Invite.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    token = new_token()
    invite = Invite(
        email=email,
        token_hash=hash_token(token, settings.signing_key),
        invited_by_id=actor.id,
        expires_at=now + timedelta(days=settings.invite_expiry_days),
    )
    invite.roles = roles
    db.add(invite)
    await db.flush()
    audit.record(
        db,
        action="invite.created",
        object_table="invites",
        object_id=invite.id,
        user_id=actor.id,
        source=AuditSource.API,
        new_value={"email": email, "roles": sorted(r.key for r in roles)},
    )
    return IssuedInvite(token=token, invite=invite)


async def list_pending_invites(db: AsyncSession) -> list[Invite]:
    result = await db.execute(
        select(Invite)
        .where(
            Invite.accepted_at.is_(None), Invite.revoked_at.is_(None), Invite.expires_at > _now()
        )
        .order_by(Invite.created_at.desc())
        .options(selectinload(Invite.roles))
    )
    return list(result.scalars())


async def revoke_invite(db: AsyncSession, *, actor: User, invite_id: uuid.UUID) -> None:
    invite = await db.get(Invite, invite_id)
    if invite is None or invite.accepted_at is not None or invite.revoked_at is not None:
        raise NotFound("No pending invite with that ID.")
    invite.revoked_at = _now()
    audit.record(
        db,
        action="invite.revoked",
        object_table="invites",
        object_id=invite.id,
        user_id=actor.id,
        source=AuditSource.API,
    )


async def find_valid_invite(db: AsyncSession, token: str, *, settings: Settings) -> Invite:
    result = await db.execute(
        select(Invite)
        .where(Invite.token_hash == hash_token(token, settings.signing_key))
        .options(selectinload(Invite.roles).selectinload(Role.permissions))
    )
    invite = result.scalar_one_or_none()
    if (
        invite is None
        or invite.accepted_at is not None
        or invite.revoked_at is not None
        or invite.expires_at <= _now()
    ):
        raise NotFound("This invite link is invalid or has expired. Ask an admin for a new one.")
    return invite


async def accept_invite(
    db: AsyncSession, *, token: str, name: str, password: str, settings: Settings
) -> User:
    invite = await find_valid_invite(db, token, settings=settings)
    if await get_user_by_email(db, invite.email) is not None:
        raise Conflict("This person already has an account.")
    if not name.strip():
        raise ValidationFailed("Enter your name.")
    check_password_policy(password, email=invite.email)
    user = User(email=invite.email, name=name.strip(), password_hash=hash_password(password))
    user.roles = list(invite.roles)
    db.add(user)
    await db.flush()
    invite.accepted_at = _now()
    invite.accepted_user_id = user.id
    audit.record(
        db,
        action="user.created",
        object_table="users",
        object_id=user.id,
        user_id=user.id,
        source=AuditSource.API,
        new_value={"email": user.email, "roles": sorted(r.key for r in user.roles)},
        reason=f"accepted invite {invite.id}",
    )
    return user
