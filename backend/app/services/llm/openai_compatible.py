"""OpenAI-compatible chat completions provider (any base URL).

Works for OpenAI and xAI Grok (`https://api.x.ai/v1`). Configured via
LLM_API_KEY / XAI_API_KEY, LLM_BASE_URL, LLM_MODEL, LLM_TIMEOUT_SECONDS.
Uses httpx — no SDK required.

xAI docs: structured outputs via response_format type ``json_object`` or
``json_schema`` (https://docs.x.ai/developers/model-capabilities/text/structured-outputs).
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.services.llm.base import LLMProvider
from app.services.llm.errors import LLMServiceError

logger = logging.getLogger(__name__)

# Well-known defaults (overridable via LLM_BASE_URL / LLM_MODEL).
OPENAI_DEFAULT_BASE_URL = "https://api.openai.com/v1"
OPENAI_DEFAULT_MODEL = "gpt-4o-mini"
XAI_DEFAULT_BASE_URL = "https://api.x.ai/v1"
# Fast non-reasoning default for pathology extraction/explain latency.
# Override with LLM_MODEL (e.g. grok-4.7) when you want a slower reasoning model.
XAI_DEFAULT_MODEL = "grok-4.20-0309-non-reasoning"


class OpenAICompatibleProvider(LLMProvider):
    """Chat Completions against any OpenAI-compatible gateway (OpenAI, xAI, …)."""

    name = "openai"

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = OPENAI_DEFAULT_BASE_URL,
        model: str = OPENAI_DEFAULT_MODEL,
        timeout: float = 120.0,
        provider_name: str = "openai",
    ) -> None:
        if not api_key:
            raise ValueError("LLM_API_KEY is required for hosted LLM providers")
        self.name = provider_name
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout

    def model_id(self) -> str:
        return self._model

    def _build_payload(
        self,
        *,
        system: str,
        user: str,
        response_format: str | None,
        temperature: float,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self._model,
            "temperature": temperature,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        # Both OpenAI and xAI accept json_object for well-formed JSON responses.
        if response_format == "json":
            payload["response_format"] = {"type": "json_object"}
        return payload

    async def complete(
        self,
        *,
        system: str,
        user: str,
        response_format: str | None = "json",
        temperature: float = 0.0,
    ) -> str:
        payload = self._build_payload(
            system=system,
            user=user,
            response_format=response_format,
            temperature=temperature,
        )

        # PHI policy: do not log full user content (may contain report text).
        logger.info(
            "openai_compatible.complete provider=%s model=%s base_url=%s timeout=%s user_chars=%d",
            self.name,
            self._model,
            self._base_url,
            self._timeout,
            len(user),
        )

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(
                    f"{self._base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                resp.raise_for_status()
                data = resp.json()
        except httpx.TimeoutException as exc:
            raise LLMServiceError(
                f"The language model timed out after {int(self._timeout)} seconds. "
                "Try again, raise LLM_TIMEOUT_SECONDS, or switch to a faster model "
                "(e.g. grok-4.20-0309-non-reasoning).",
                code="llm_timeout",
            ) from exc
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code if exc.response is not None else "?"
            raise LLMServiceError(
                f"The language model returned an HTTP {status} error. "
                "Check the API key, model id, and provider status.",
                code="llm_http_error",
            ) from exc
        except httpx.HTTPError as exc:
            raise LLMServiceError(
                "Could not reach the language model service. Please try again shortly.",
                code="llm_network_error",
            ) from exc

        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMServiceError(
                "The language model returned an unexpected response shape.",
                code="llm_bad_response",
            ) from exc
