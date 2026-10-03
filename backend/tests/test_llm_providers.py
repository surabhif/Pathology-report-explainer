"""Tests for LLM provider factory + OpenAI-compatible HTTP client (mocked).

No real API keys or network calls — httpx is patched.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.config import Settings
from app.services.llm.factory import get_llm_provider
from app.services.llm.mock import MockProvider
from app.services.llm.openai_compatible import (
    XAI_DEFAULT_BASE_URL,
    XAI_DEFAULT_MODEL,
    OpenAICompatibleProvider,
)


def test_default_provider_is_mock_when_no_key():
    settings = Settings(
        llm_provider="mock",
        llm_model="mock-heuristic-v1",
        llm_api_key="",
        xai_api_key="",
    )
    provider = get_llm_provider(settings)
    assert isinstance(provider, MockProvider)
    assert provider.provider_id() == "mock"


def test_xai_falls_back_to_mock_without_api_key():
    settings = Settings(
        llm_provider="xai",
        llm_model="grok-4.7",
        llm_api_key="",
        xai_api_key="",
    )
    provider = get_llm_provider(settings)
    assert isinstance(provider, MockProvider)


def test_xai_provider_uses_sensible_defaults():
    settings = Settings(
        llm_provider="xai",
        llm_model="mock-heuristic-v1",  # leftover default → replace with grok-4.7
        llm_api_key="test-xai-key",
        llm_base_url="",
        xai_api_key="",
    )
    provider = get_llm_provider(settings)
    assert isinstance(provider, OpenAICompatibleProvider)
    assert provider.provider_id() == "xai"
    assert provider.model_id() == XAI_DEFAULT_MODEL
    assert provider._base_url == XAI_DEFAULT_BASE_URL


def test_xai_provider_respects_custom_model_and_base_url():
    settings = Settings(
        llm_provider="xai",
        llm_model="grok-4.6",
        llm_api_key="test-xai-key",
        llm_base_url="https://api.x.ai/v1",
    )
    provider = get_llm_provider(settings)
    assert provider.model_id() == "grok-4.6"
    assert provider._base_url == "https://api.x.ai/v1"


def test_xai_accepts_xai_api_key_alias():
    settings = Settings(
        llm_provider="xai",
        llm_model="grok-4.7",
        llm_api_key="",
        xai_api_key="from-xai-env",
    )
    provider = get_llm_provider(settings)
    assert isinstance(provider, OpenAICompatibleProvider)
    assert provider.provider_id() == "xai"


def test_xai_overrides_openai_base_url_leftover():
    settings = Settings(
        llm_provider="xai",
        llm_model="grok-4.7",
        llm_api_key="k",
        llm_base_url="https://api.openai.com/v1",
    )
    provider = get_llm_provider(settings)
    assert provider._base_url == XAI_DEFAULT_BASE_URL


@pytest.mark.asyncio
async def test_openai_compatible_posts_json_object_to_xai_endpoint():
    """Mock HTTP: verify Authorization, URL, model, and response_format for xAI."""
    provider = OpenAICompatibleProvider(
        api_key="secret-xai",
        base_url=XAI_DEFAULT_BASE_URL,
        model=XAI_DEFAULT_MODEL,
        provider_name="xai",
    )

    fake_response = MagicMock()
    fake_response.raise_for_status = MagicMock()
    fake_response.json.return_value = {
        "choices": [{"message": {"content": '{"diagnosis_or_histologic_type": null}'}}]
    }

    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None
    mock_client.post = AsyncMock(return_value=fake_response)

    with patch("app.services.llm.openai_compatible.httpx.AsyncClient", return_value=mock_client):
        text = await provider.complete(
            system="Extract JSON.",
            user="REPORT: invasive ductal carcinoma",
            response_format="json",
        )

    assert "diagnosis_or_histologic_type" in text
    mock_client.post.assert_awaited_once()
    args, kwargs = mock_client.post.await_args
    assert args[0] == "https://api.x.ai/v1/chat/completions"
    assert kwargs["headers"]["Authorization"] == "Bearer secret-xai"
    body = kwargs["json"]
    assert body["model"] == "grok-4.7"
    assert body["response_format"] == {"type": "json_object"}
    assert body["messages"][0]["role"] == "system"
    assert body["messages"][1]["role"] == "user"


@pytest.mark.asyncio
async def test_openai_compatible_complete_json_parses_payload():
    provider = OpenAICompatibleProvider(
        api_key="k",
        base_url=XAI_DEFAULT_BASE_URL,
        model="grok-4.7",
        provider_name="xai",
    )
    fake_response = MagicMock()
    fake_response.raise_for_status = MagicMock()
    fake_response.json.return_value = {
        "choices": [{"message": {"content": '{"grade": {"value": "2", "quote": "grade 2"}}'}}]
    }
    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None
    mock_client.post = AsyncMock(return_value=fake_response)

    with patch("app.services.llm.openai_compatible.httpx.AsyncClient", return_value=mock_client):
        data = await provider.complete_json(system="s", user="u")

    assert data["grade"]["value"] == "2"


def test_unknown_provider_raises():
    settings = Settings(llm_provider="not-a-vendor", llm_api_key="k")
    with pytest.raises(ValueError, match="Unknown LLM_PROVIDER"):
        get_llm_provider(settings)
