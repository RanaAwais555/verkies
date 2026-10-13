"""/system/providers (PROVIDER_SPEC.md §5): which optional providers are switched on, so a
missing key shows up as a degraded mode instead of silently missing data. Configuration only;
nothing here makes an outside call.

/system/backups (slice 7.2): how the backup service's steps last went, for admins."""

from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.auth.deps import AppSettings, CurrentUser, DbSession, require_permission
from app.auth.models import User
from app.system import backups
from app.system.models import BackupRun

router = APIRouter(prefix="/system", tags=["system"])


class ProviderStatus(BaseModel):
    name: str
    status: Literal["ok", "degraded", "off"]
    detail: str


@router.get("/providers")
async def providers(_: CurrentUser, settings: AppSettings) -> list[ProviderStatus]:
    key = settings.companies_house_api_key
    has_key = bool(key and key.get_secret_value())
    has_sra_key = bool(settings.sra_api_key and settings.sra_api_key.get_secret_value())
    safe_browsing = settings.safe_browsing_api_key
    has_safe_browsing_key = bool(safe_browsing and safe_browsing.get_secret_value())
    return [
        ProviderStatus(
            name="JavaScript rendering",
            status="ok" if settings.render_enabled else "off",
            detail="Headless Chromium in the worker renders thin pages"
            if settings.render_enabled
            else "Off: thin JavaScript pages are analysed as served",
        ),
        ProviderStatus(
            name="AI writing",
            status="ok" if settings.ai_provider != "none" else "off",
            detail=f"Ollama ({settings.ollama_model}); every claim is checked against evidence"
            if settings.ai_provider != "none"
            else "Off: briefs use template mode",
        ),
        ProviderStatus(
            name="Job boards and news feeds",
            status="ok",
            detail="Greenhouse, Lever, Ashby, Workable and company feeds, when the site links them",
        ),
        ProviderStatus(
            name="Companies House",
            status="ok" if has_key else "degraded",
            detail="UK registry facts and directors, by the number on the company's site"
            if has_key
            else "No API key: registry facts are skipped (set VROS_COMPANIES_HOUSE_API_KEY)",
        ),
        ProviderStatus(
            name="Web search",
            status="ok" if settings.search_provider != "none" else "off",
            detail="SearXNG (self-hosted) finds candidate company websites"
            if settings.search_provider != "none"
            else "Off: Discover offers CSV import only (start Compose with --profile search)",
        ),
        ProviderStatus(
            name="SRA register",
            status="ok" if has_sra_key else "off",
            detail="Every SRA-regulated law firm, kept in VROS and refreshed daily"
            if has_sra_key
            else "Off: Discover cannot search law firms (set VROS_SRA_API_KEY)",
        ),
        ProviderStatus(
            name="Wikidata",
            status="ok" if settings.wikidata_enabled else "off",
            detail="Company facts by official website" if settings.wikidata_enabled else "Off",
        ),
        ProviderStatus(
            name="Wayback Machine",
            status="ok" if settings.website_archive_enabled else "off",
            detail="How long a researched site's homepage has gone unchanged"
            if settings.website_archive_enabled
            else "Off: site age is not checked",
        ),
        ProviderStatus(
            name="Safe Browsing",
            status="ok" if has_safe_browsing_key else "off",
            detail="Whether Google warns visitors away from a researched site"
            if has_safe_browsing_key
            else "Off: not checked (set VROS_SAFE_BROWSING_API_KEY)",
        ),
    ]


Admin = Annotated[User, Depends(require_permission("config.manage", "users.manage"))]


class BackupRunOut(BaseModel):
    status: Literal["ok", "failed", "skipped"]
    started_at: datetime
    finished_at: datetime
    bytes: int | None
    detail: str | None

    @classmethod
    def of(cls, run: BackupRun | None) -> "BackupRunOut | None":
        if run is None:
            return None
        return cls(
            status=run.status,  # type: ignore[arg-type]
            started_at=run.started_at,
            finished_at=run.finished_at,
            bytes=run.bytes,
            detail=run.detail,
        )


class BackupStatusOut(BaseModel):
    kind: str
    label: str
    latest: BackupRunOut | None
    last_ok: BackupRunOut | None


@router.get("/backups")
async def backup_status(_: Admin, db: DbSession) -> list[BackupStatusOut]:
    return [
        BackupStatusOut(
            kind=s.kind,
            label=backups.LABELS[s.kind],
            latest=BackupRunOut.of(s.latest),
            last_ok=BackupRunOut.of(s.last_ok),
        )
        for s in await backups.status(db)
    ]
