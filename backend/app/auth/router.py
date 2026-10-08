"""/auth: sign in and out, current user, password change, accepting an invite."""

from fastapi import APIRouter, Request, Response, status

from app.auth import service
from app.auth.deps import (
    AppSettings,
    CurrentSession,
    CurrentUser,
    DbSession,
    clear_auth_cookies,
    cookie_names,
    set_auth_cookies,
)
from app.auth.schemas import (
    InviteAccept,
    InviteInfo,
    InviteToken,
    LoginRequest,
    PasswordChange,
    SessionOut,
    UserOut,
)
from app.core.errors import NotAuthenticated

router = APIRouter(prefix="/auth", tags=["auth"])


def _client(request: Request) -> tuple[str | None, str | None]:
    host = request.client.host if request.client else None
    return host, request.headers.get("user-agent")


@router.post("/login")
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    db: DbSession,
    settings: AppSettings,
) -> SessionOut:
    try:
        user = await service.authenticate(
            db, email=body.email, password=body.password, settings=settings
        )
    except NotAuthenticated:
        await db.commit()  # keep the failed-attempt count and audit entry
        raise
    ip, agent = _client(request)
    issued = service.issue_session(db, user, settings=settings, ip=ip, user_agent=agent)
    await db.commit()
    csrf = set_auth_cookies(response, issued.token, settings)
    return SessionOut(user=UserOut.of(user), csrf_token=csrf)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    session: CurrentSession, response: Response, db: DbSession, settings: AppSettings
) -> None:
    await service.revoke_session(db, session)
    await db.commit()
    clear_auth_cookies(response, settings)


@router.get("/me")
async def me(user: CurrentUser, request: Request, settings: AppSettings) -> SessionOut:
    _, csrf_name = cookie_names(settings)
    return SessionOut(user=UserOut.of(user), csrf_token=request.cookies.get(csrf_name, ""))


@router.post("/password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(body: PasswordChange, session: CurrentSession, db: DbSession) -> None:
    await service.change_password(
        db,
        user=session.user,
        current_session=session,
        current=body.current_password,
        new=body.new_password,
    )
    await db.commit()


@router.post("/invites/inspect")
async def inspect_invite(body: InviteToken, db: DbSession, settings: AppSettings) -> InviteInfo:
    invite = await service.find_valid_invite(db, body.token, settings=settings)
    return InviteInfo(
        email=invite.email, roles=sorted(r.key for r in invite.roles), expires_at=invite.expires_at
    )


@router.post("/invites/accept")
async def accept_invite(
    body: InviteAccept,
    request: Request,
    response: Response,
    db: DbSession,
    settings: AppSettings,
) -> SessionOut:
    user = await service.accept_invite(
        db, token=body.token, name=body.name, password=body.password, settings=settings
    )
    ip, agent = _client(request)
    issued = service.issue_session(db, user, settings=settings, ip=ip, user_agent=agent)
    await db.commit()
    csrf = set_auth_cookies(response, issued.token, settings)
    return SessionOut(user=UserOut.of(user), csrf_token=csrf)
