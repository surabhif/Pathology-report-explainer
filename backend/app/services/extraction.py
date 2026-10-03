"""Structured JSON extraction of pathology facts via LLM provider + schema validation."""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from app.config import get_settings
from app.schemas import FactSheet
from app.services.llm.base import LLMProvider
from app.services.llm.mock import extract_facts_heuristic

logger = logging.getLogger(__name__)


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


async def extract_facts(
    report_text: str,
    provider: LLMProvider,
    *,
    prompt_name: str = "extract_v1.txt",
) -> tuple[FactSheet, str]:
    """Run extraction; return (FactSheet, raw prompt version tag).

    PHI: logs only report_id/length externally — here we log char count only.
    """
    system = load_prompt(prompt_name)
    user = f"Extract structured pathology facts as JSON.\n\nREPORT:\n{report_text}"
    logger.info(
        "extraction.start provider=%s model=%s report_chars=%d",
        provider.provider_id(),
        provider.model_id(),
        len(report_text),
    )
    try:
        raw = await provider.complete_json(system=system, user=user, temperature=0.0)
        facts = validate_facts(raw)
    except (ValidationError, json.JSONDecodeError, KeyError) as exc:
        # Fallback to heuristics so the pipeline never hard-fails for MVP demos.
        logger.warning("extraction.fallback reason=%s", type(exc).__name__)
        facts = validate_facts(extract_facts_heuristic(report_text))
    return facts, prompt_name.replace(".txt", "")
