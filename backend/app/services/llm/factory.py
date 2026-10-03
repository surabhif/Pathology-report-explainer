"""Factory: build LLMProvider from Settings / env."""

from __future__ import annotations

from app.config import Settings, get_settings
from app.services.llm.base import LLMProvider
from app.services.llm.mock import MockProvider
from app.services.llm.openai_compatible import OpenAICompatibleProvider


def get_llm_provider(settings: Settings | None = None) -> LLMProvider:
    settings = settings or get_settings()
    provider = (settings.llm_provider or "mock").strip().lower()

    if provider in {"mock", "heuristic", "demo"}:
        return MockProvider(model=settings.llm_model if settings.llm_model.startswith("mock") else "mock-heuristic-v1")

    if provider in {"openai", "openai_compatible", "compatible"}:
        return OpenAICompatibleProvider(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            model=settings.llm_model,
        )

    raise ValueError(f"Unknown LLM_PROVIDER={provider!r}; use 'mock' or 'openai'")
