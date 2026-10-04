"""Provider-agnostic LLM interface.

Interview note: callers never import OpenAI SDKs directly — they go through
LLMProvider so we can swap MockProvider (deterministic demos / CI) for any
OpenAI-compatible endpoint via env vars.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class LLMProvider(ABC):
    """Minimal chat-completion style interface."""

    name: str = "base"

    @abstractmethod
    async def complete(
        self,
        *,
        system: str,
        user: str,
        response_format: str | None = "json",
        temperature: float = 0.0,
    ) -> str:
        """Return model text (usually JSON string)."""

    @abstractmethod
    def model_id(self) -> str:
        """Identifier recorded on Generation rows."""

    def provider_id(self) -> str:
        return self.name

    async def complete_json(
        self,
        *,
        system: str,
        user: str,
        temperature: float = 0.0,
    ) -> dict[str, Any]:
        import json

        raw = await self.complete(
            system=system,
            user=user,
            response_format="json",
            temperature=temperature,
        )
        return json.loads(raw)
