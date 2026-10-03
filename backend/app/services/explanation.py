"""Grounded plain-language explanation generation."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from app.config import get_settings
from app.schemas import ExplanationPayload, FactSheet
from app.services.llm.base import LLMProvider
from app.services.llm.mock import build_explanation

logger = logging.getLogger(__name__)


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
) -> tuple[ExplanationPayload, str]:
    """Produce grounded explanation sentences from facts + report."""
    system = load_prompt(prompt_name)
    facts_json = facts.model_dump_json(indent=2)
    user = (
        "Write a plain-language explanation (6th–8th grade) as JSON with grounded sentences.\n\n"
        f"FACTS_JSON:\n{facts_json}\n\nREPORT:\n{report_text}"
    )
    logger.info(
        "explanation.start provider=%s model=%s fact_keys=%d",
        provider.provider_id(),
        provider.model_id(),
        sum(1 for v in facts.model_dump().values() if v is not None),
    )
    try:
        raw = await provider.complete_json(system=system, user=user, temperature=0.0)
        explanation = validate_explanation(raw)
    except (ValidationError, json.JSONDecodeError, KeyError, TypeError) as exc:
        logger.warning("explanation.fallback reason=%s", type(exc).__name__)
        explanation = validate_explanation(build_explanation(facts.model_dump()))
    return explanation, prompt_name.replace(".txt", "")
