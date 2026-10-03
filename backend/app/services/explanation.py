"""Grounded plain-language explanation generation."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from app.config import get_settings
from app.schemas import ExplanationPayload, FactSheet
from app.services.checks import unsupported_sentences
from app.services.grounding import annotate_explanation_grounding
from app.services.llm.base import LLMProvider
from app.services.llm.errors import LLMServiceError
from app.services.llm.mock import build_explanation

logger = logging.getLogger(__name__)

STRICT_RETRY_SUFFIX = """
RETRY REQUIRED — grounding failed on the previous draft.
Some sentences had an empty quote or a quote that was NOT found word-for-word in the REPORT.
Rewrite the full explanation JSON. Every sentence MUST have:
- non-empty "quote" copied exactly (contiguous substring) from the REPORT below
- non-empty "source_fact_keys"
If you cannot ground a claim with a real report quote, omit that sentence.
Do not invent procedure narrative that is not supported by a quote.
""".strip()


@dataclass
class ExplanationResult:
    explanation: ExplanationPayload
    prompt_tag: str
    used_fallback: bool = False
    fallback_reason: str | None = None
    retried: bool = False
    grounding_check: dict[str, Any] = field(default_factory=dict)


def load_prompt(name: str = "explain_v1.txt") -> str:
    path: Path = get_settings().prompts_dir / name
    return path.read_text(encoding="utf-8")


def validate_explanation(data: dict[str, Any]) -> ExplanationPayload:
    return ExplanationPayload.model_validate(data)


def _finalize(
    explanation: ExplanationPayload,
    report_text: str,
    *,
    prompt_tag: str,
    used_fallback: bool = False,
    fallback_reason: str | None = None,
    retried: bool = False,
) -> ExplanationResult:
    annotated = annotate_explanation_grounding(explanation.model_dump(), report_text)
    payload = validate_explanation(annotated)
    check = unsupported_sentences(annotated, report_text)
    return ExplanationResult(
        explanation=payload,
        prompt_tag=prompt_tag,
        used_fallback=used_fallback,
        fallback_reason=fallback_reason,
        retried=retried,
        grounding_check=check,
    )


async def generate_explanation(
    report_text: str,
    facts: FactSheet,
    provider: LLMProvider,
    *,
    prompt_name: str = "explain_v1.txt",
    force_heuristic: bool = False,
) -> ExplanationResult:
    """Produce grounded explanation sentences from facts + report.

    ``force_heuristic`` is used when extraction already fell back — keep the
    whole generation honestly labeled as mock rather than mixing providers.

    When a hosted model returns unsupported sentences (empty quote or quote not
    found word-for-word in the report), we attempt **one** stricter retry and
    record ``retried=True`` on the result.
    """
    system = load_prompt(prompt_name)
    facts_json = facts.model_dump_json(indent=2)
    user = (
        "Write a plain-language explanation (6th–8th grade) as JSON with grounded sentences.\n\n"
        f"FACTS_JSON:\n{facts_json}\n\nREPORT:\n{report_text}"
    )
    prompt_tag = prompt_name.replace(".txt", "")
    logger.info(
        "explanation.start provider=%s model=%s fact_keys=%d",
        provider.provider_id(),
        provider.model_id(),
        sum(1 for v in facts.model_dump().values() if v is not None),
    )

    if force_heuristic or provider.provider_id() == "mock":
        explanation = validate_explanation(build_explanation(facts.model_dump()))
        return _finalize(
            explanation,
            report_text,
            prompt_tag=prompt_tag,
            used_fallback=force_heuristic,
            fallback_reason="paired_with_extraction_fallback" if force_heuristic else None,
            retried=False,
        )

    try:
        raw = await provider.complete_json(system=system, user=user, temperature=0.0)
        first = validate_explanation(raw)
    except LLMServiceError:
        raise
    except (ValidationError, json.JSONDecodeError, KeyError, TypeError) as exc:
        reason = f"explanation_{type(exc).__name__}"
        logger.warning(
            "explanation.fallback requested_provider=%s requested_model=%s reason=%s",
            provider.provider_id(),
            provider.model_id(),
            reason,
        )
        explanation = validate_explanation(build_explanation(facts.model_dump()))
        return _finalize(
            explanation,
            report_text,
            prompt_tag=prompt_tag,
            used_fallback=True,
            fallback_reason=reason,
            retried=False,
        )

    first_result = _finalize(first, report_text, prompt_tag=prompt_tag, retried=False)
    if first_result.grounding_check.get("pass"):
        return first_result

    # One automatic retry with a stricter grounding instruction.
    logger.info(
        "explanation.retry unsupported_count=%s",
        first_result.grounding_check.get("unsupported_count"),
    )
    flagged = first_result.grounding_check.get("flagged") or []
    problem_lines = "\n".join(
        f"- [{f.get('index')}] {f.get('sentence')!r} reasons={f.get('reasons')}" for f in flagged
    )
    retry_user = (
        f"{user}\n\n{STRICT_RETRY_SUFFIX}\n\n"
        f"Previous unsupported sentences:\n{problem_lines or '(none listed)'}"
    )
    try:
        raw2 = await provider.complete_json(system=system, user=retry_user, temperature=0.0)
        second = validate_explanation(raw2)
        second_result = _finalize(second, report_text, prompt_tag=prompt_tag, retried=True)
    except LLMServiceError:
        # Keep the first draft rather than failing the whole explain after a timeout on retry.
        logger.warning("explanation.retry_failed keeping_first_draft")
        first_result.retried = True  # we attempted
        return first_result
    except (ValidationError, json.JSONDecodeError, KeyError, TypeError) as exc:
        logger.warning("explanation.retry_invalid reason=%s keeping_first_draft", type(exc).__name__)
        first_result.retried = True
        return first_result

    # Prefer the retry when it is at least as well grounded.
    first_rate = float(first_result.grounding_check.get("support_rate") or 0.0)
    second_rate = float(second_result.grounding_check.get("support_rate") or 0.0)
    if second_rate >= first_rate:
        return second_result
    # Keep the better first draft, but record that a retry was attempted.
    first_result.retried = True
    return first_result
