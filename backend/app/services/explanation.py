"""Grounded plain-language explanation generation."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from app.config import get_settings
from app.schemas import ExplanationPayload, FactSheet
from app.services.llm.base import LLMProvider
from app.services.llm.errors import LLMServiceError
from app.services.llm.mock import build_explanation

logger = logging.getLogger(__name__)


@dataclass
class ExplanationResult:
    explanation: ExplanationPayload
    prompt_tag: str
    used_fallback: bool = False
    fallback_reason: str | None = None


def load_prompt(name: str = "explain_v1.txt") -> str:
    path: Path = get_settings().prompts_dir / name
    return path.read_text(encoding="utf-8")


def validate_explanation(data: dict[str, Any]) -> ExplanationPayload:
    return ExplanationPayload.model_validate(data)


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
        return ExplanationResult(
            explanation=explanation,
            prompt_tag=prompt_tag,
            used_fallback=force_heuristic,
            fallback_reason="paired_with_extraction_fallback" if force_heuristic else None,
        )

    try:
        raw = await provider.complete_json(system=system, user=user, temperature=0.0)
        explanation = validate_explanation(raw)
        return ExplanationResult(
            explanation=explanation,
            prompt_tag=prompt_tag,
            used_fallback=False,
        )
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
        return ExplanationResult(
            explanation=explanation,
            prompt_tag=prompt_tag,
            used_fallback=True,
            fallback_reason=reason,
        )
