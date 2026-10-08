"""/system/providers (PROVIDER_SPEC.md §5): which optional providers are switched on, so a
missing key shows up as a degraded mode instead of silently missing data. Configuration only;
nothing here makes an outside call."""

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from app.auth.deps import AppSettings, CurrentUser

router = APIRouter(prefix="/system", tags=["system"])


class ProviderStatus(BaseModel):
    name: str
    status: Literal["ok", "degraded", "off"]
    detail: str


@router.get("/providers")
async def providers(_: CurrentUser, settings: AppSettings) -> list[ProviderStatus]:
    key = settings.companies_house_api_key
    has_key = bool(key and key.get_secret_value())
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
            name="Wikidata",
            status="ok" if settings.wikidata_enabled else "off",
            detail="Company facts by official website" if settings.wikidata_enabled else "Off",
        ),
    ]
