"""/reports/* dashboards and /saved-views (master context §13, slice 3.3)."""

import uuid
from typing import Annotated
from urllib.parse import parse_qsl

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, or_, select

from app.audit import service as audit
from app.auth.deps import AppSettings, DbSession, require_permission
from app.auth.models import User
from app.core.enums import AuditSource
from app.core.errors import NotFound, PermissionDenied
from app.reports import service
from app.reports.models import SavedView
from app.reports.service import Dashboard, Period

router = APIRouter(tags=["reports"])

Member = Annotated[User, Depends(require_permission("accounts.read", "accounts.read_own"))]
Analyst = Annotated[User, Depends(require_permission("accounts.read", "prospects.review"))]
Manager = Annotated[User, Depends(require_permission("reports.team"))]

# Pages a saved view may point at: the ones that keep their filters in the address.
VIEW_PAGES = (
    "/leads",
    "/accounts",
    "/pipeline",
    "/tasks",
    "/follow-ups",
    "/reports",
    "/discover",
    "/duplicates",
    "/research",
)
SHARE = "config.manage"


@router.get("/reports/sales")
async def sales_dashboard(
    user: Member, db: DbSession, settings: AppSettings, period: Period = "90d", mine: bool = False
) -> Dashboard:
    return await service.sales(db, user=user, settings=settings, period=period, mine=mine)


@router.get("/reports/lead-intelligence")
async def lead_intelligence_dashboard(
    user: Analyst, db: DbSession, period: Period = "90d"
) -> Dashboard:
    return await service.lead_intelligence(db, user=user, period=period)


@router.get("/reports/management")
async def management_dashboard(user: Manager, db: DbSession, period: Period = "90d") -> Dashboard:
    return await service.management(db, user=user, period=period)


# --- saved views -------------------------------------------------------------------------------


class SavedViewOut(BaseModel):
    id: uuid.UUID
    name: str
    path: str
    query: str
    shared: bool
    can_delete: bool

    @classmethod
    def of(cls, v: SavedView, user: User) -> "SavedViewOut":
        shared = v.user_id is None
        return cls(
            id=v.id,
            name=v.name,
            path=v.path,
            query=v.query,
            shared=shared,
            can_delete=(SHARE in user.permission_keys) if shared else v.user_id == user.id,
        )


class NewSavedView(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    path: str = Field(max_length=200)
    query: str = Field(default="", max_length=1000)
    shared: bool = False

    @field_validator("path")
    @classmethod
    def _known_page(cls, path: str) -> str:
        path = path.rstrip("/") or "/"
        if not any(path == p or path.startswith(p + "/") for p in VIEW_PAGES):
            raise ValueError("A saved view can only point at a VROS page that keeps its filters.")
        return path

    @field_validator("query")
    @classmethod
    def _plain_query(cls, query: str) -> str:
        query = query.removeprefix("?")
        try:
            parse_qsl(query, strict_parsing=bool(query))
        except ValueError as exc:
            raise ValueError("That is not a page's filter string.") from exc
        return query


@router.get("/saved-views")
async def saved_views(user: Member, db: DbSession) -> list[SavedViewOut]:
    rows = (
        await db.execute(
            select(SavedView)
            .where(or_(SavedView.user_id.is_(None), SavedView.user_id == user.id))
            .order_by(SavedView.user_id.is_not(None), SavedView.position, SavedView.created_at)
        )
    ).scalars()
    return [SavedViewOut.of(v, user) for v in rows]


@router.post("/saved-views", status_code=201)
async def save_view(body: NewSavedView, user: Member, db: DbSession) -> SavedViewOut:
    if body.shared and SHARE not in user.permission_keys:
        raise PermissionDenied("Only someone who manages configuration can share a view.")
    owner = None if body.shared else user.id
    position = (
        await db.execute(
            select(func.coalesce(func.max(SavedView.position), -1)).where(
                SavedView.user_id.is_(None) if owner is None else SavedView.user_id == owner
            )
        )
    ).scalar_one()
    view = SavedView(
        user_id=owner,
        name=body.name.strip(),
        path=body.path,
        query=body.query,
        position=position + 1,
        created_by_id=user.id,
    )
    db.add(view)
    await db.flush()
    if owner is None:
        audit.record(
            db,
            action="saved_view.shared",
            object_table="saved_views",
            object_id=view.id,
            user_id=user.id,
            source=AuditSource.API,
            new_value={"name": view.name, "path": view.path, "query": view.query},
        )
    await db.commit()
    return SavedViewOut.of(view, user)


@router.delete("/saved-views/{view_id}", status_code=204)
async def delete_view(view_id: uuid.UUID, user: Member, db: DbSession) -> Response:
    view = await db.get(SavedView, view_id)
    if view is None or (view.user_id is not None and view.user_id != user.id):
        raise NotFound("Saved view not found.")
    if view.user_id is None:
        if SHARE not in user.permission_keys:
            raise PermissionDenied("Only someone who manages configuration can remove a team view.")
        audit.record(
            db,
            action="saved_view.removed",
            object_table="saved_views",
            object_id=view.id,
            user_id=user.id,
            source=AuditSource.API,
            old_value={"name": view.name, "path": view.path, "query": view.query},
        )
    await db.delete(view)
    await db.commit()
    return Response(status_code=204)
