"""Typed application settings, read from the environment (prefix ``VROS_``).

Production fails closed: insecure or missing values stop the app at startup instead of
running a team system on a public domain with development secrets.
"""

from enum import StrEnum
from functools import lru_cache
from typing import Annotated, Self
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

DEV_DATABASE_PASSWORD = "vros"  # noqa: S105 - the known development default we refuse in production
MIN_SECRET_KEY_LENGTH = 32


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

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
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
        if problems:
            raise ValueError("insecure production configuration: " + "; ".join(problems))
        return self

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


@lru_cache
def get_settings() -> Settings:
    return Settings()
