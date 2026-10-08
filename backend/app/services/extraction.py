"""Structured JSON extraction of pathology facts via LLM provider + schema validation."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from app.config import get_settings
from app.schemas import FactSheet
from app.services.grounding import recompute_fact_offsets
from app.services.llm.base import LLMProvider
from app.services.llm.errors import LLMServiceError
from app.services.llm.mock import extract_facts_heuristic

logger = logging.getLogger(__name__)


@dataclass
class ExtractionResult:
    facts: FactSheet
    prompt_tag: str
    used_fallback: bool = False
    fallback_reason: str | None = None


@lru_cache
def load_extraction_schema() -> dict[str, Any]:
    path = get_settings().config_dir / "extraction_schema.json"
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def load_prompt(name: str = "extract_v1.txt") -> str:
    path: Path = get_settings().prompts_dir / name
    return path.read_text(encoding="utf-8")


def validate_facts(data: dict[str, Any]) -> FactSheet:
    """Validate against Pydantic FactSheet (mirrors extraction_schema.json)."""
    return FactSheet.model_validate(data)


def facts_with_recomputed_offsets(data: dict[str, Any], report_text: str) -> FactSheet:
    """Validate facts, then replace LLM character offsets with text-search spans."""
    validated = validate_facts(data)
    corrected = recompute_fact_offsets(validated.model_dump(), report_text)
    return FactSheet.model_validate(corrected)


async def extract_facts(
    report_text: str,
    provider: LLMProvider,
    *,
    prompt_name: str = "extract_v1.txt",
) -> ExtractionResult:
    """Run extraction; return facts plus honest fallback metadata.

    Network/timeouts raise ``LLMServiceError`` (surfaced to the UI).
    Invalid JSON/schema falls back to heuristics and is labeled as mock fallback —
    never silently attributed to the hosted provider.

    Character offsets are always recomputed from the source text; LLM-written
    ``start_char``/``end_char`` values are never persisted as-is.
    """
    system = load_prompt(prompt_name)
    user = f"Extract structured pathology facts as JSON.\n\nREPORT:\n{report_text}"
    prompt_tag = prompt_name.replace(".txt", "")
    logger.info(
        "extraction.start provider=%s model=%s report_chars=%d",
        provider.provider_id(),
        provider.model_id(),
        len(report_text),
    )

    # Pure mock provider: heuristics are the intended path, not a "fallback".
    if provider.provider_id() == "mock":
        facts = facts_with_recomputed_offsets(extract_facts_heuristic(report_text), report_text)
        return ExtractionResult(facts=facts, prompt_tag=prompt_tag, used_fallback=False)

    try:
        raw = await provider.complete_json(system=system, user=user, temperature=0.0)
        facts = facts_with_recomputed_offsets(raw, report_text)
        return ExtractionResult(facts=facts, prompt_tag=prompt_tag, used_fallback=False)
    except LLMServiceError:
        raise
    except (ValidationError, json.JSONDecodeError, KeyError, TypeError) as exc:
        reason = f"extraction_{type(exc).__name__}"
        logger.warning(
            "extraction.fallback requested_provider=%s requested_model=%s reason=%s",
            provider.provider_id(),
            provider.model_id(),
            reason,
        )
        facts = facts_with_recomputed_offsets(extract_facts_heuristic(report_text), report_text)
        return ExtractionResult(
            facts=facts,
            prompt_tag=prompt_tag,
            used_fallback=True,
            fallback_reason=reason,
        )
