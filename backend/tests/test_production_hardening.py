"""Tests for production-hardening: timeouts, honest fallbacks, demo tokens, rate limit IP."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.config import get_settings
from app.db import _make_engine
from app.seed import _resolve_demo_users
from app.services.extraction import extract_facts
from app.services.llm.errors import LLMServiceError
from app.services.llm.openai_compatible import OpenAICompatibleProvider
from app.services.rate_limit import client_ip_key


@pytest.mark.asyncio
async def test_timeout_raises_llm_service_error():
    provider = OpenAICompatibleProvider(
        api_key="k",
        base_url="https://api.x.ai/v1",
        model="grok-4.20-0309-non-reasoning",
        timeout=1.0,
        provider_name="xai",
    )
    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None
    mock_client.post = AsyncMock(side_effect=httpx.TimeoutException("timed out"))

    with patch("app.services.llm.openai_compatible.httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(LLMServiceError) as ei:
            await provider.complete(system="s", user="u")
    assert ei.value.code == "llm_timeout"
    assert "timed out" in ei.value.message.lower() or "timeout" in ei.value.message.lower()


@pytest.mark.asyncio
async def test_http_error_raises_llm_service_error():
    provider = OpenAICompatibleProvider(
        api_key="k",
        base_url="https://api.x.ai/v1",
        model="m",
        provider_name="xai",
    )
    req = httpx.Request("POST", "https://api.x.ai/v1/chat/completions")
    resp = httpx.Response(500, request=req)
    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None
    mock_client.post = AsyncMock(side_effect=httpx.HTTPStatusError("boom", request=req, response=resp))

    with patch("app.services.llm.openai_compatible.httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(LLMServiceError) as ei:
            await provider.complete(system="s", user="u")
    assert ei.value.code == "llm_http_error"


@pytest.mark.asyncio
async def test_extraction_fallback_is_labeled_not_as_xai():
    """Invalid model JSON → heuristic facts + used_fallback=True (not labeled as xAI)."""
    import json

    class BadJSONProvider:
        name = "xai"

        def provider_id(self) -> str:
            return "xai"

        def model_id(self) -> str:
            return "grok-test"

        async def complete_json(self, **_kwargs):
            raise json.JSONDecodeError("Expecting value", "not-json", 0)

    result = await extract_facts(
        "Invasive ductal carcinoma. Grade 2. Tumor size 2.5 cm.",
        BadJSONProvider(),  # type: ignore[arg-type]
    )
    assert result.used_fallback is True
    assert result.fallback_reason
    assert "JSONDecodeError" in (result.fallback_reason or "")
    assert result.facts.diagnosis_or_histologic_type is not None


def test_demo_tokens_skipped_in_production_without_env(monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("DEMO_ADMIN_TOKEN", raising=False)
    monkeypatch.delenv("DEMO_ANNOTATOR_TOKEN", raising=False)
    monkeypatch.delenv("DEMO_CLINICIAN_TOKEN", raising=False)
    get_settings.cache_clear()
    assert _resolve_demo_users() is None
    get_settings.cache_clear()


def test_demo_tokens_from_env_in_production(monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DEMO_ADMIN_TOKEN", "prod-admin-secret")
    monkeypatch.setenv("DEMO_ANNOTATOR_TOKEN", "prod-ann-secret")
    monkeypatch.setenv("DEMO_CLINICIAN_TOKEN", "prod-clin-secret")
    get_settings.cache_clear()
    users = _resolve_demo_users()
    assert users is not None
    assert {u["invite_token"] for u in users} == {
        "prod-admin-secret",
        "prod-ann-secret",
        "prod-clin-secret",
    }
    assert "DEMO_ADMIN_TOKEN" not in {u["invite_token"] for u in users}
    get_settings.cache_clear()


def test_demo_tokens_local_defaults_in_development(monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.delenv("DEMO_ADMIN_TOKEN", raising=False)
    monkeypatch.delenv("DEMO_ANNOTATOR_TOKEN", raising=False)
    monkeypatch.delenv("DEMO_CLINICIAN_TOKEN", raising=False)
    get_settings.cache_clear()
    users = _resolve_demo_users()
    assert users is not None
    assert any(u["invite_token"] == "DEMO_ADMIN_TOKEN" for u in users)
    get_settings.cache_clear()


def test_engine_uses_pool_pre_ping():
    eng = _make_engine()
    assert getattr(eng.pool, "_pre_ping", None) is True
    eng.dispose()


def test_rate_limit_ignores_forwarded_when_untrusted(monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("TRUST_PROXY_HEADERS", "false")
    get_settings.cache_clear()

    class FakeClient:
        host = "10.0.0.5"

    class FakeRequest:
        client = FakeClient()
        headers = {"x-forwarded-for": "1.2.3.4, 10.0.0.1"}

    assert client_ip_key(FakeRequest()) == "10.0.0.5"  # type: ignore[arg-type]
    get_settings.cache_clear()


def test_rate_limit_uses_forwarded_when_trusted(monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("TRUST_PROXY_HEADERS", "true")
    get_settings.cache_clear()

    class FakeClient:
        host = "10.0.0.5"

    class FakeRequest:
        client = FakeClient()
        headers = {"x-forwarded-for": "1.2.3.4, 10.0.0.1"}

    assert client_ip_key(FakeRequest()) == "1.2.3.4"  # type: ignore[arg-type]
    get_settings.cache_clear()
