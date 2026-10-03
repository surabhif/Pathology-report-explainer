"""Tests for quote grounding, unsupported-sentence checks, and explain retry."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.schemas import FactSheet
from app.services.checks import unsupported_sentences
from app.services.explanation import generate_explanation
from app.services.grounding import annotate_explanation_grounding, assess_sentence_grounding


BRCA2_SNIPPET = """
FINAL DIAGNOSIS — LEFT MASTECTOMY
Procedure: Left total mastectomy and axillary lymph node dissection
Histologic type: Invasive lobular carcinoma.
""".strip()


def test_empty_quote_always_unsupported_even_without_keys():
    explanation = {
        "sentences": [
            {
                "sentence": "The doctor removed your left breast and some lymph nodes in surgery.",
                "source_fact_keys": [],
                "quote": "",
            }
        ]
    }
    result = unsupported_sentences(explanation, BRCA2_SNIPPET)
    assert result["pass"] is False
    assert result["unsupported_count"] == 1
    assert 0 in result["unsupported_indices"]
    reasons = result["flagged"][0]["reasons"]
    assert "missing_quote" in reasons
    assert "missing_source_fact_keys" in reasons


def test_whitespace_quote_counts_as_missing():
    explanation = {
        "sentences": [
            {
                "sentence": "Surgery was done.",
                "source_fact_keys": ["diagnosis_or_histologic_type"],
                "quote": "   ",
            }
        ]
    }
    result = unsupported_sentences(explanation, BRCA2_SNIPPET)
    assert "missing_quote" in result["flagged"][0]["reasons"]


def test_paraphrase_quote_not_in_report():
    explanation = {
        "sentences": [
            {
                "sentence": "The doctor removed your left breast.",
                "source_fact_keys": ["diagnosis_or_histologic_type"],
                "quote": "the doctor removed your left breast",
            }
        ]
    }
    result = unsupported_sentences(explanation, BRCA2_SNIPPET)
    assert result["pass"] is False
    assert "quote_not_in_report" in result["flagged"][0]["reasons"]


def test_verbatim_quote_is_supported():
    explanation = {
        "sentences": [
            {
                "sentence": "The tissue type is invasive lobular carcinoma.",
                "source_fact_keys": ["diagnosis_or_histologic_type"],
                "quote": "Invasive lobular carcinoma",
            }
        ]
    }
    result = unsupported_sentences(explanation, BRCA2_SNIPPET)
    assert result["pass"] is True
    assert result["unsupported_count"] == 0


def test_annotate_explanation_grounding_sets_metadata():
    raw = {
        "sentences": [
            {
                "sentence": "Ungrounded claim.",
                "source_fact_keys": ["grade"],
                "quote": "",
            },
            {
                "sentence": "Grounded claim.",
                "source_fact_keys": ["diagnosis_or_histologic_type"],
                "quote": "Invasive lobular carcinoma",
            },
        ]
    }
    annotated = annotate_explanation_grounding(raw, BRCA2_SNIPPET)
    assert annotated["sentences"][0]["grounding"]["ok"] is False
    assert annotated["sentences"][0]["quote"] is None
    assert annotated["sentences"][1]["grounding"]["ok"] is True


@pytest.mark.asyncio
async def test_explanation_retries_once_when_ungrounded():
    facts = FactSheet.model_validate(
        {
            "diagnosis_or_histologic_type": {
                "value": "Invasive lobular carcinoma",
                "quote": "Invasive lobular carcinoma",
                "start_char": 0,
                "end_char": 26,
            }
        }
    )

    bad = {
        "sentences": [
            {
                "sentence": "The doctor removed your left breast and some lymph nodes in surgery.",
                "source_fact_keys": [],
                "quote": "",
            }
        ]
    }
    good = {
        "sentences": [
            {
                "sentence": "The cancer type is invasive lobular carcinoma.",
                "source_fact_keys": ["diagnosis_or_histologic_type"],
                "quote": "Invasive lobular carcinoma",
            }
        ]
    }

    class HostedProvider:
        def provider_id(self) -> str:
            return "xai"

        def model_id(self) -> str:
            return "grok-test"

        complete_json = AsyncMock(side_effect=[bad, good])

    provider = HostedProvider()
    result = await generate_explanation(BRCA2_SNIPPET, facts, provider)  # type: ignore[arg-type]
    assert result.retried is True
    assert result.grounding_check.get("pass") is True
    assert provider.complete_json.await_count == 2
    second_kwargs = provider.complete_json.await_args_list[1].kwargs
    assert "RETRY REQUIRED" in second_kwargs["user"]


@pytest.mark.asyncio
async def test_mock_provider_does_not_retry():
    facts = FactSheet.model_validate({})

    class MockProv:
        def provider_id(self) -> str:
            return "mock"

        def model_id(self) -> str:
            return "mock-heuristic-v1"

        complete_json = AsyncMock()

    provider = MockProv()
    result = await generate_explanation(BRCA2_SNIPPET, facts, provider)  # type: ignore[arg-type]
    assert result.retried is False
    provider.complete_json.assert_not_awaited()


def test_assess_sentence_grounding_helper():
    reasons = assess_sentence_grounding(
        {"sentence": "x", "source_fact_keys": ["grade"], "quote": None},
        BRCA2_SNIPPET,
    )
    assert reasons == ["missing_quote"]
