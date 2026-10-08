"""/catalogue: Verkies' services and reference projects, plus /team for owner pickers.

Reference-project profiles start with only what the public site states. An admin completes
them here; similarity stays Unknown for a project until its profile is marked complete.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.audit import service as audit
from app.auth.deps import CurrentUser, DbSession, require_permission
from app.auth.models import User
from app.catalogue.models import ReferenceProject, Service
from app.core.enums import AuditSource
from app.core.errors import NotFound, ValidationFailed

router = APIRouter(tags=["catalogue"])

Admin = Annotated[User, Depends(require_permission("config.manage"))]


class ServiceOut(BaseModel):
    id: uuid.UUID
    key: str
    name: str
    description: str
    solves: list[str]
    confirmed: bool
    is_active: bool
    source_url: str | None


class ReferenceProjectOut(BaseModel):
    id: uuid.UUID
    name: str
    industry: str | None
    business_model: str | None
    problem: str | None
    technologies: list[str]
    growth_stage: str | None
    buyer_type: str | None
    workflow_notes: str | None
    status: str | None
    website_url: str | None
    source_url: str | None
    services: list[str]
    profile_complete: bool

    @classmethod
    def of(cls, p: ReferenceProject) -> "ReferenceProjectOut":
        return cls(
            id=p.id,
            name=p.name,
            industry=p.industry,
            business_model=p.business_model,
            problem=p.problem,
            technologies=list(p.technologies or []),
            growth_stage=p.growth_stage,
            buyer_type=p.buyer_type,
            workflow_notes=p.workflow_notes,
            status=p.status,
            website_url=p.website_url,
            source_url=p.source_url,
            services=sorted(s.key for s in p.services),
            profile_complete=p.profile_complete,
        )


class ReferenceProjectUpdate(BaseModel):
    industry: str | None = Field(default=None, max_length=120)
    business_model: str | None = Field(default=None, max_length=120)
    problem: str | None = Field(default=None, max_length=4000)
    technologies: list[str] | None = Field(default=None, max_length=40)
    growth_stage: str | None = Field(default=None, max_length=60)
    buyer_type: str | None = Field(default=None, max_length=120)
    workflow_notes: str | None = Field(default=None, max_length=4000)
    status: str | None = Field(default=None, max_length=120)
    website_url: str | None = Field(default=None, max_length=2000)
    services: list[str] | None = None
    profile_complete: bool | None = None


class TeamMemberOut(BaseModel):
    id: uuid.UUID
    name: str
    email: str


@router.get("/team")
async def team(_: CurrentUser, db: DbSession) -> list[TeamMemberOut]:
    """Active team members, for choosing an owner."""
    users = (
        await db.execute(select(User).where(User.is_active.is_(True)).order_by(User.name))
    ).scalars()
    return [TeamMemberOut(id=u.id, name=u.name, email=u.email) for u in users]


@router.get("/catalogue/services")
async def services(_: CurrentUser, db: DbSession) -> list[ServiceOut]:
    rows = (await db.execute(select(Service).order_by(Service.created_at, Service.key))).scalars()
    return [ServiceOut.model_validate(s, from_attributes=True) for s in rows]


@router.get("/catalogue/reference-projects")
async def reference_projects(_: CurrentUser, db: DbSession) -> list[ReferenceProjectOut]:
    rows = (await db.execute(select(ReferenceProject).order_by(ReferenceProject.name))).scalars()
    return [ReferenceProjectOut.of(p) for p in rows]


@router.patch("/catalogue/reference-projects/{project_id}")
async def update_reference_project(
    project_id: uuid.UUID, body: ReferenceProjectUpdate, user: Admin, db: DbSession
) -> ReferenceProjectOut:
    project = await db.get(ReferenceProject, project_id)
    if project is None:
        raise NotFound("Reference project not found.")
    changes = body.model_dump(exclude_unset=True)
    old = ReferenceProjectOut.of(project).model_dump(mode="json")
    if "services" in changes:
        keys = changes.pop("services") or []
        found = list((await db.execute(select(Service).where(Service.key.in_(keys)))).scalars())
        unknown = set(keys) - {s.key for s in found}
        if unknown:
            raise ValidationFailed(f"Unknown services: {', '.join(sorted(unknown))}.")
        project.services = found
    for key, value in changes.items():
        if isinstance(value, str):
            value = value.strip() or None
        setattr(project, key, value)
    if project.profile_complete and not (project.industry and project.problem and project.services):
        # Similarity compares industry, problem and services; a profile missing one would
        # produce a score from nothing.
        raise ValidationFailed(
            "A complete profile needs an industry, the problem solved and at least one service."
        )
    new = ReferenceProjectOut.of(project).model_dump(mode="json")
    audit.record(
        db,
        action="reference_project.updated",
        object_table="reference_projects",
        object_id=project.id,
        user_id=user.id,
        source=AuditSource.API,
        old_value={k: v for k, v in old.items() if old[k] != new[k]},
        new_value={k: v for k, v in new.items() if old[k] != new[k]},
    )
    await db.commit()
    return ReferenceProjectOut.model_validate(new)
