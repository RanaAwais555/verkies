from typing import Any

import pytest
from pydantic import ValidationError

from app.config import ConfigurationError, Environment, Settings, load_settings

SECURE_PROD: dict[str, Any] = {
    "environment": "production",
    "public_url": "https://vros.example.com",
    "secret_key": "x" * 32,
    "database_url": "postgresql+psycopg://vros:s3cure-pass@postgres:5432/vros",
}


def _settings(**overrides: Any) -> Settings:
    return Settings(_env_file=None, **overrides)


def test_development_defaults_point_at_local_services() -> None:
    settings = _settings()
    assert settings.database_url.startswith("postgresql+psycopg://")
    assert settings.redis_url.startswith("redis://")
    assert settings.allowed_origins == ["http://localhost:3000"]
    assert settings.docs_enabled is True


def test_environment_variables_override_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VROS_ENVIRONMENT", "development")
    monkeypatch.setenv("VROS_REDIS_URL", "redis://cache:6379/2")
    settings = _settings()
    assert settings.environment is Environment.DEVELOPMENT
    assert settings.redis_url == "redis://cache:6379/2"


def test_cors_origins_accept_comma_separated_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VROS_CORS_ORIGINS", "http://a.test, https://b.test ,")
    assert _settings().allowed_origins == ["http://a.test", "https://b.test"]


def test_health_timeout_must_be_positive() -> None:
    with pytest.raises(ValidationError, match="greater than 0"):
        _settings(health_check_timeout=0)


@pytest.mark.parametrize("url", ["vros.example.com", "ftp://vros.example.com", "https://"])
def test_public_url_must_be_absolute_http(url: str) -> None:
    with pytest.raises(ValidationError, match="absolute http"):
        _settings(public_url=url)


def test_secure_production_config_is_accepted() -> None:
    settings = _settings(**SECURE_PROD)
    assert settings.is_production
    assert settings.public_host == "vros.example.com"
    assert settings.docs_enabled is False
    assert settings.allowed_origins == []  # single origin behind the proxy


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"secret_key": None}, "VROS_SECRET_KEY"),
        ({"secret_key": "short"}, "VROS_SECRET_KEY"),
        ({"public_url": "http://vros.example.com"}, "https"),
        ({"database_url": "postgresql+psycopg://vros:vros@postgres/vros"}, "database password"),
        ({"database_url": "postgresql+psycopg://vros@postgres/vros"}, "database password"),
        ({"fetch_private_allowlist": ["10.0.0.0/8"]}, "PRIVATE_ALLOWLIST"),
        ({"fetch_host_overrides": ["shop.test=127.0.0.1"]}, "HOST_OVERRIDES"),
    ],
)
def test_insecure_production_config_is_refused(override: dict[str, Any], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        _settings(**{**SECURE_PROD, **override})


def test_secret_key_is_not_exposed_in_repr() -> None:
    assert "x" * 32 not in repr(_settings(**SECURE_PROD))


def test_configuration_error_never_echoes_secret_values(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VROS_ENVIRONMENT", "production")
    monkeypatch.setenv("VROS_PUBLIC_URL", "https://vros.example.com")
    monkeypatch.setenv("VROS_SECRET_KEY", "leaky-but-too-short")
    monkeypatch.setenv("VROS_DATABASE_URL", "postgresql+psycopg://vros:hunter2-db-pass@db/vros")
    with pytest.raises(ConfigurationError) as caught:
        load_settings()
    message = str(caught.value)
    assert "VROS_SECRET_KEY must be set" in message
    assert "leaky-but-too-short" not in message
    assert "hunter2-db-pass" not in message
    assert caught.value.__cause__ is None
    assert caught.value.__suppress_context__ is True
