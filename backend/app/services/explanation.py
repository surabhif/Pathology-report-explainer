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
from app.services.checks import reading_level_check, unsupported_sentences
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
Do NOT stitch distant fragments with ellipses ("..." / "…"); use separate sentences instead.
If you cannot ground a claim with a real report quote, omit that sentence.
Do not invent procedure narrative that is not supported by a quote.
""".strip()

READABILITY_RETRY_SUFFIX = """
RETRY REQUIRED — reading level is too hard.
The previous draft was not simpler than the source report and/or exceeded the
6th–8th grade target. Rewrite EVERY sentence in simpler, shorter words.
Keep the same facts. Every quote MUST remain a contiguous word-for-word
substring from the REPORT (no ellipsis stitching). Prefer short sentences.
Do not raise the grade level above the source report.
""".strip()

TARGET_MAX_GRADE = 8.5


@dataclass
class ExplanationResult:
    explanation: ExplanationPayload
    prompt_tag: str
    used_fallback: bool = False
    fallback_reason: str | None = None
    retried: bool = False
    grounding_check: dict[str, Any] = field(default_factory=dict)
    reading_level_check: dict[str, Any] = field(default_factory=dict)
    readability_retried: bool = False


def load_prompt(name: str = "explain_v1.txt") -> str:
    path: Path = get_settings().prompts_dir / name
    return path.read_text(encoding="utf-8")


def validate_explanation(data: dict[str, Any]) -> ExplanationPayload:
    return ExplanationPayload.model_validate(data)


def _reading_level_ok(check: dict[str, Any]) -> bool:
    """Pass when explanation is below the source grade and within the target band."""
    return bool(check.get("simpler_than_original")) and bool(check.get("meets_target"))


def _finalize(
    explanation: ExplanationPayload,
    report_text: str,
    *,
    prompt_tag: str,
    used_fallback: bool = False,
    fallback_reason: str | None = None,
    retried: bool = False,
    readability_retried: bool = False,
) -> ExplanationResult:
    annotated = annotate_explanation_grounding(explanation.model_dump(), report_text)
    payload = validate_explanation(annotated)
    check = unsupported_sentences(annotated, report_text)
    rl = reading_level_check(report_text, annotated, target_max_grade=TARGET_MAX_GRADE)
    # Fold readability into the stored checks snapshot for Results / UI.
    check = {
        **check,
        "reading_level": rl,
        "readability_retried": readability_retried,
    }
    return ExplanationResult(
        explanation=payload,
        prompt_tag=prompt_tag,
        used_fallback=used_fallback,
        fallback_reason=fallback_reason,
        retried=retried,
        grounding_check=check,
        reading_level_check=rl,
        readability_retried=readability_retried,
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
    found word-for-word in the report), we attempt **one** stricter retry.
    After grounding, if the Flesch-Kincaid grade is not below the source *and*
    within the 6th–8th grade target, we attempt **one** readability retry.
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

    result = _finalize(first, report_text, prompt_tag=prompt_tag, retried=False)
    if not result.grounding_check.get("pass"):
        # One automatic retry with a stricter grounding instruction.
        logger.info(
            "explanation.retry unsupported_count=%s",
            result.grounding_check.get("unsupported_count"),
        )
        flagged = result.grounding_check.get("flagged") or []
        problem_lines = "\n".join(
            f"- [{f.get('index')}] {f.get('sentence')!r} reasons={f.get('reasons')}"
            for f in flagged
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
            logger.warning("explanation.retry_failed keeping_first_draft")
            result.retried = True
            second_result = None
        except (ValidationError, json.JSONDecodeError, KeyError, TypeError) as exc:
            logger.warning(
                "explanation.retry_invalid reason=%s keeping_first_draft", type(exc).__name__
            )
            result.retried = True
            second_result = None

        if second_result is not None:
            first_rate = float(result.grounding_check.get("support_rate") or 0.0)
            second_rate = float(second_result.grounding_check.get("support_rate") or 0.0)
            if second_rate >= first_rate:
                result = second_result
            else:
                result.retried = True

    # Readability pass: explanation must be simpler than source and ≤ target.
    if not _reading_level_ok(result.reading_level_check):
        logger.info(
            "explanation.readability_retry orig=%s expl=%s",
            result.reading_level_check.get("original_grade"),
            result.reading_level_check.get("explanation_grade"),
        )
        rl = result.reading_level_check
        retry_user = (
            f"{user}\n\n{READABILITY_RETRY_SUFFIX}\n\n"
            f"Previous grades: original={rl.get('original_grade')}, "
            f"explanation={rl.get('explanation_grade')} "
            f"(target ≤ {TARGET_MAX_GRADE}; must be simpler than the source)."
        )
        try:
            raw3 = await provider.complete_json(system=system, user=retry_user, temperature=0.0)
            simpler = validate_explanation(raw3)
            simple_result = _finalize(
                simpler,
                report_text,
                prompt_tag=prompt_tag,
                retried=result.retried,
                readability_retried=True,
            )
            # Prefer the readability retry when grounding is at least as good
            # and reading level improved (or already ok).
            if (
                float(simple_result.grounding_check.get("support_rate") or 0.0)
                >= float(result.grounding_check.get("support_rate") or 0.0)
            ):
                return simple_result
            result.readability_retried = True
            result.grounding_check = {
                **result.grounding_check,
                "readability_retried": True,
                "reading_level": result.reading_level_check,
                "readability_retry_kept_prior": True,
            }
        except LLMServiceError:
            logger.warning("explanation.readability_retry_failed")
            result.readability_retried = True
            result.grounding_check = {
                **result.grounding_check,
                "readability_retried": True,
            }
        except (ValidationError, json.JSONDecodeError, KeyError, TypeError) as exc:
            logger.warning(
                "explanation.readability_retry_invalid reason=%s", type(exc).__name__
            )
            result.readability_retried = True
            result.grounding_check = {
                **result.grounding_check,
                "readability_retried": True,
            }

    return result
