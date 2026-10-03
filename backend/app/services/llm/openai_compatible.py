"""OpenAI-compatible chat completions provider (any base URL).

Configured via LLM_API_KEY, LLM_BASE_URL, LLM_MODEL.
Uses httpx — no openai SDK dependency required.
"""

from __future__ import annotations

import logging

import httpx

from app.services.llm.base import LLMProvider

logger = logging.getLogger(__name__)


class OpenAICompatibleProvider(LLMProvider):
    name = "openai"

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = "https://api.openai.com/v1",
        model: str = "gpt-4o-mini",
        timeout: float = 60.0,
    ) -> None:
        if not api_key:
            raise ValueError("LLM_API_KEY is required for openai provider")
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout

    def model_id(self) -> str:
        return self._model

    async def complete(
        self,
        *,
        system: str,
        user: str,
        response_format: str | None = "json",
        temperature: float = 0.0,
    ) -> str:
        payload: dict = {
            "model": self._model,
            "temperature": temperature,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        if response_format == "json":
            payload["response_format"] = {"type": "json_object"}

        # PHI policy: do not log full user content (may contain report text).
        logger.info(
            "openai_compatible.complete model=%s base_url=%s user_chars=%d",
            self._model,
            self._base_url,
            len(user),
        )

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

        return data["choices"][0]["message"]["content"]
