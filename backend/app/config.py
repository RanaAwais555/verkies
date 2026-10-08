"""Typed application settings, read from the environment (prefix ``VROS_``).

Production fails closed: insecure or missing values stop the app at startup instead of
running a team system on a public domain with development secrets.
"""

from enum import StrEnum
from functools import lru_cache
from typing import Annotated, Literal, Self
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, ValidationError, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

DEV_DATABASE_PASSWORD = "vros"  # noqa: S105 - the known development default we refuse in production
MIN_SECRET_KEY_LENGTH = 32
# Used only outside production when no secret is configured.
DEV_SIGNING_KEY = b"vros-development-signing-key-not-secret"


class Environment(StrEnum):
    DEVELOPMENT = "development"
    TEST = "test"
    PRODUCTION = "production"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="VROS_", env_file=".env", extra="ignore")

    environment: Environment = Environment.DEVELOPMENT
    app_version: str = "0.1.0"
    log_level: str = "INFO"

    # The URL people use to reach VROS, e.g. https://vros.verkies.co. Drives allowed hosts,
    # cookie security and the default CORS origin.
    public_url: str = "http://localhost:3000"

    # Signs sessions and tokens. Required in production.
    secret_key: SecretStr | None = None

    database_url: str = f"postgresql+psycopg://vros:{DEV_DATABASE_PASSWORD}@localhost:5432/vros"
    redis_url: str = "redis://localhost:6379/0"

    # Comma-separated in the environment. Only needed when the frontend is served from a
    # different origin than the API (development); production is single-origin behind Caddy.
    cors_origins: Annotated[list[str], NoDecode] = Field(default_factory=list)

    # OpenAPI docs at /api/v1/docs. Defaults to on outside production.
    api_docs_enabled: bool | None = None

    # Seconds each readiness dependency check may take before it counts as down.
    health_check_timeout: float = Field(default=2.0, gt=0)

    # Team sessions (SECURITY.md §1). A session ends after this much inactivity, or at the
    # absolute limit, whichever comes first.
    session_idle_minutes: int = Field(default=12 * 60, gt=0)
    session_max_days: int = Field(default=14, gt=0)
    invite_expiry_days: int = Field(default=7, gt=0)
    # After this many consecutive wrong passwords the account is locked for the lockout period.
    login_max_failures: int = Field(default=5, gt=0)
    login_lockout_minutes: int = Field(default=15, gt=0)

    # Approval (PRODUCT_SPEC.md §5): the next-action task is due this many business days later.
    task_due_business_days: int = Field(default=2, ge=0, le=30)

    # Crawler (PROVIDER_SPEC.md §4). Identifies itself and how to reach Verkies.
    crawler_contact_url: str = "https://www.verkies.co"
    crawl_max_pages: int = Field(default=15, gt=0, le=100)
    crawl_max_bytes_per_response: int = Field(default=2 * 1024 * 1024, gt=0)
    crawl_max_total_bytes: int = Field(default=15 * 1024 * 1024, gt=0)
    crawl_max_redirects: int = Field(default=5, ge=0, le=10)
    crawl_request_timeout_seconds: float = Field(default=15.0, gt=0)
    crawl_wall_clock_seconds: float = Field(default=120.0, gt=0)
    crawl_min_interval_seconds: float = Field(default=1.0, ge=0)
    crawl_concurrency: int = Field(default=2, ge=1, le=4)
    crawl_cache_days: int = Field(default=7, ge=0)
    crawl_allowed_ports: Annotated[list[int], NoDecode] = Field(default_factory=lambda: [80, 443])
    # Private networks the fetcher may reach. For tests only; refused in production.
    fetch_private_allowlist: Annotated[list[str], NoDecode] = Field(default_factory=list)
    # host=address pairs answered without DNS, e.g. "shop.test=127.0.0.1". For local
    # end-to-end runs only; refused in production.
    fetch_host_overrides: Annotated[list[str], NoDecode] = Field(default_factory=list)
    # JavaScript rendering with headless Chromium, for pages whose static HTML is too thin.
    render_enabled: bool = True
    chromium_executable: str | None = None

    # Company registries (slice 2.3). Companies House needs a free API key from
    # developer.company-information.service.gov.uk; without one that lookup is skipped.
    companies_house_api_key: SecretStr | None = None
    wikidata_enabled: bool = True

    # Optional local AI for brief wording (AI_SPEC.md). "none" = template mode only.
    ai_provider: Literal["none", "ollama"] = "none"
    ollama_url: str = "http://ollama:11434"
    ollama_model: str = "granite4.2:8b"
    ollama_num_ctx: int = Field(default=8192, ge=2048)
    ai_timeout_seconds: float = Field(default=120.0, gt=0)

    # Where fetched bodies are stored (StorageProvider). Docker mounts a volume here.
    storage_dir: str = "./var/storage"

    @field_validator(
        "cors_origins",
        "fetch_private_allowlist",
        "fetch_host_overrides",
        "crawl_allowed_ports",
        mode="before",
    )
    @classmethod
    def _split_csv(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("public_url")
    @classmethod
    def _valid_public_url(cls, value: str) -> str:
        parts = urlsplit(value)
        if parts.scheme not in {"http", "https"} or not parts.hostname:
            raise ValueError("public_url must be an absolute http(s) URL")
        return value.rstrip("/")

    @model_validator(mode="after")
    def _production_is_secure(self) -> Self:
        if self.environment is not Environment.PRODUCTION:
            return self
        problems: list[str] = []
        if (
            self.secret_key is None
            or len(self.secret_key.get_secret_value()) < MIN_SECRET_KEY_LENGTH
        ):
            problems.append(
                f"VROS_SECRET_KEY must be set to at least {MIN_SECRET_KEY_LENGTH} characters"
            )
        if urlsplit(self.public_url).scheme != "https":
            problems.append("VROS_PUBLIC_URL must use https")
        if urlsplit(self.database_url).password in (None, "", DEV_DATABASE_PASSWORD):
            problems.append("VROS_DATABASE_URL must use a non-default database password")
        if self.fetch_private_allowlist:
            problems.append("VROS_FETCH_PRIVATE_ALLOWLIST must be empty (it disables SSRF checks)")
        if self.fetch_host_overrides:
            problems.append("VROS_FETCH_HOST_OVERRIDES must be empty (it bypasses DNS)")
        if problems:
            raise ValueError("insecure production configuration: " + "; ".join(problems))
        return self

    @property
    def signing_key(self) -> bytes:
        """Key for hashing session and invite tokens. Production guarantees a real secret."""
        if self.secret_key is not None:
            return self.secret_key.get_secret_value().encode()
        return DEV_SIGNING_KEY

    @property
    def secure_cookies(self) -> bool:
        return urlsplit(self.public_url).scheme == "https"

    @property
    def crawler_user_agent(self) -> str:
        return f"VROSBot/{self.app_version} (+{self.crawler_contact_url})"

    @property
    def is_production(self) -> bool:
        return self.environment is Environment.PRODUCTION

    @property
    def public_host(self) -> str:
        host = urlsplit(self.public_url).hostname
        assert host is not None  # guaranteed by _valid_public_url
        return host

    @property
    def docs_enabled(self) -> bool:
        return (
            self.api_docs_enabled if self.api_docs_enabled is not None else not self.is_production
        )

    @property
    def allowed_origins(self) -> list[str]:
        return self.cors_origins or ([] if self.is_production else [self.public_url])


class ConfigurationError(RuntimeError):
    """Settings are invalid. The message names each problem but never echoes input values,
    which may include secrets (pydantic's own errors print the raw input)."""


def load_settings() -> Settings:
    try:
        return Settings()
    except ValidationError as exc:
        problems = []
        for error in exc.errors(include_input=False, include_url=False):
            field = ".".join(str(part) for part in error["loc"]) or "settings"
            problems.append(f"{field}: {error['msg']}")
        raise ConfigurationError("invalid configuration: " + " | ".join(problems)) from None


@lru_cache
def get_settings() -> Settings:
    return load_settings()
