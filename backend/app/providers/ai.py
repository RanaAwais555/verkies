"""AI provider interface (PROVIDER_SPEC.md §2, AI_SPEC.md §5-6).

AI is optional. With no provider configured the brief is written in template mode and
everything else works. Ollama runs locally, so company text stays on Verkies' machines.
"""

import json
from typing import Any, Protocol

import httpx

from app.config import Settings
from app.providers.errors import ProviderError, ProviderUnavailable


class AIProvider(Protocol):
    name: str
    model: str

    async def generate_json(
        self, *, system: str, prompt: str, schema: dict[str, Any]
    ) -> dict[str, Any]: ...


class NullAIProvider:
    name = "none"
    model = ""

    async def generate_json(
        self, *, system: str, prompt: str, schema: dict[str, Any]
    ) -> dict[str, Any]:
        raise ProviderUnavailable("No AI provider configured.")


class OllamaProvider:
    """Ollama's /api/chat with JSON-schema constrained output and an explicit context size
    (Ollama defaults to 4,096 tokens, too small for a brief)."""

    name = "ollama"

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        num_ctx: int,
        timeout_seconds: float,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.num_ctx = num_ctx
        self.timeout_seconds = timeout_seconds
        self.transport = transport

    async def generate_json(
        self, *, system: str, prompt: str, schema: dict[str, Any]
    ) -> dict[str, Any]:
        body = {
            "model": self.model,
            "stream": False,
            "format": schema,
            "options": {"num_ctx": self.num_ctx, "temperature": 0.2},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
        }
        try:
            async with httpx.AsyncClient(
                transport=self.transport, timeout=self.timeout_seconds, trust_env=False
            ) as client:
                response = await client.post(f"{self.base_url}/api/chat", json=body)
        except httpx.HTTPError as exc:
            raise ProviderUnavailable(f"Ollama unreachable: {type(exc).__name__}") from exc
        if response.status_code != 200:
            raise ProviderError(f"Ollama returned {response.status_code}", code="ai_error")
        try:
            content = response.json()["message"]["content"]
            parsed = json.loads(content)
        except (KeyError, ValueError, TypeError) as exc:
            raise ProviderError("Ollama returned malformed JSON", code="ai_bad_output") from exc
        if not isinstance(parsed, dict):
            raise ProviderError("Ollama returned a non-object", code="ai_bad_output")
        return parsed


def build_ai_provider(settings: Settings) -> AIProvider:
    if settings.ai_provider == "ollama":
        return OllamaProvider(
            base_url=settings.ollama_url,
            model=settings.ollama_model,
            num_ctx=settings.ollama_num_ctx,
            timeout_seconds=settings.ai_timeout_seconds,
        )
    return NullAIProvider()
