"""Factory: build LLMProvider from Settings / env.

Provider ids:
  - mock  — deterministic heuristics (default; no API key)
  - xai   — xAI Grok via OpenAI-compatible API (https://api.x.ai/v1)
  - openai / openai_compatible — OpenAI or any compatible gateway

When a hosted provider is selected but no API key is set, we fall back to
mock so local demos and CI keep working without credentials.
"""

from __future__ import annotations

import logging

from app.config import Settings, get_settings
from app.services.llm.base import LLMProvider
from app.services.llm.mock import MockProvider
from app.services.llm.openai_compatible import (
    OPENAI_DEFAULT_BASE_URL,
    OPENAI_DEFAULT_MODEL,
    XAI_DEFAULT_BASE_URL,
    XAI_DEFAULT_MODEL,
    OpenAICompatibleProvider,
)

logger = logging.getLogger(__name__)


def _looks_like_placeholder_model(model: str) -> bool:
    """True when LLM_MODEL is empty or still a default from another provider."""
    m = (model or "").strip().lower()
    if not m:
        return True
    if m.startswith("mock"):
        return True
    # Cross-provider leftover defaults (e.g. LLM_MODEL still gpt-* while using xai)
    return False


def _resolve_api_key(settings: Settings, provider: str) -> str:
    """Prefer LLM_API_KEY; for xAI also accept XAI_API_KEY (xai_api_key setting)."""
    if settings.llm_api_key.strip():
        return settings.llm_api_key.strip()
    if provider in {"xai", "grok"} and settings.xai_api_key.strip():
        return settings.xai_api_key.strip()
    return ""


def _mock(settings: Settings) -> MockProvider:
    model = settings.llm_model if settings.llm_model.startswith("mock") else "mock-heuristic-v1"
    return MockProvider(model=model)


def get_llm_provider(settings: Settings | None = None) -> LLMProvider:
    settings = settings or get_settings()
    provider = (settings.llm_provider or "mock").strip().lower()

    if provider in {"mock", "heuristic", "demo"}:
        return _mock(settings)

    api_key = _resolve_api_key(settings, provider)
    if not api_key:
        # Interview-friendly: missing key must not break local/demo runs.
        logger.warning(
            "LLM_PROVIDER=%s but no API key set (LLM_API_KEY / XAI_API_KEY); using mock",
            provider,
        )
        return _mock(settings)

    if provider in {"xai", "grok"}:
        # Sensible xAI defaults; LLM_MODEL / LLM_BASE_URL remain fully configurable.
        model = settings.llm_model.strip()
        if _looks_like_placeholder_model(model) or model.startswith("gpt-"):
            model = XAI_DEFAULT_MODEL
        base_url = settings.llm_base_url.strip() or XAI_DEFAULT_BASE_URL
        if "api.openai.com" in base_url:
            base_url = XAI_DEFAULT_BASE_URL
        return OpenAICompatibleProvider(
            api_key=api_key,
            base_url=base_url,
            model=model,
            provider_name="xai",
        )

    if provider in {"openai", "openai_compatible", "compatible"}:
        model = settings.llm_model.strip() or OPENAI_DEFAULT_MODEL
        if _looks_like_placeholder_model(model):
            model = OPENAI_DEFAULT_MODEL
        base_url = settings.llm_base_url.strip() or OPENAI_DEFAULT_BASE_URL
        return OpenAICompatibleProvider(
            api_key=api_key,
            base_url=base_url,
            model=model,
            provider_name="openai",
        )

    raise ValueError(
        f"Unknown LLM_PROVIDER={provider!r}; use 'mock', 'xai', or 'openai'"
    )
