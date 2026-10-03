"""Automatic evaluation checks.

Checks implemented:
1. Field accuracy vs gold labels (exact / normalized string match)
2. TCGA / GDC metadata agreement
3. Number grounding (numbers in explanation appear in report or fact values)
4. Unsupported sentences (explanation sentences without source_fact_keys or quote in report)
5. Reading level (explanation should be easier than original; target ~6–8)
"""

from __future__ import annotations

import re
from typing import Any

from app.services.gdc import metadata_agrees_with_report
from app.services.reading_level import explanation_text_from_payload, flesch_kincaid_grade

FACT_FIELDS = [
    "diagnosis_or_histologic_type",
    "grade",
    "tumor_size",
    "margins",
    "lymph_nodes_positive",
    "lymph_nodes_examined",
    "pathologic_tnm_stage",
    "biomarkers",
]

NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")


def _norm(val: Any) -> str:
    if val is None:
        return ""
    if isinstance(val, dict):
        # biomarkers dict — stable key=value join
        parts = [f"{k}={v}".lower() for k, v in sorted(val.items())]
        return "|".join(parts)
    return str(val).strip().lower()


def field_accuracy(
    predicted: dict[str, Any] | None,
    gold: dict[str, Any] | None,
) -> dict[str, Any]:
    """Compare predicted fact sheet to gold labels field-by-field."""
    predicted = predicted or {}
    gold = gold or {}
    per_field: dict[str, Any] = {}
    correct = 0
    total = 0
    for field in FACT_FIELDS:
        g = gold.get(field)
        p = predicted.get(field)
        # Skip fields with no gold
        if g is None:
            per_field[field] = {"scored": False, "reason": "no_gold"}
            continue
        total += 1
        g_val = g.get("value") if isinstance(g, dict) else g
        p_val = p.get("value") if isinstance(p, dict) else (p if p else None)
        match = _norm(g_val) == _norm(p_val) and _norm(g_val) != ""
        # Both absent-style empty
        if _norm(g_val) == "" and _norm(p_val) == "":
            match = True
        if match:
            correct += 1
        per_field[field] = {
            "scored": True,
            "match": match,
            "gold": g_val,
            "predicted": p_val,
        }
    return {
        "correct": correct,
        "total": total,
        "accuracy": (correct / total) if total else None,
        "per_field": per_field,
    }


def extract_numbers(text: str) -> set[str]:
    return set(NUMBER_RE.findall(text or ""))


def number_grounding(
    explanation: dict[str, Any],
    report_text: str,
    facts: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Every number mentioned in the explanation should appear in the report or fact values."""
    expl_text = explanation_text_from_payload(explanation)
    expl_nums = extract_numbers(expl_text)
    allowed = extract_numbers(report_text)
    if facts:
        allowed |= extract_numbers(str(facts))
    unsupported = sorted(expl_nums - allowed)
    grounded = sorted(expl_nums & allowed)
    return {
        "explanation_numbers": sorted(expl_nums),
        "grounded": grounded,
        "ungrounded": unsupported,
        "pass": len(unsupported) == 0,
        "grounding_rate": (len(grounded) / len(expl_nums)) if expl_nums else 1.0,
    }


def unsupported_sentences(
    explanation: dict[str, Any],
    report_text: str,
) -> dict[str, Any]:
    """Flag sentences that lack source_fact_keys or whose quote is not found in the report."""
    sentences = explanation.get("sentences") or []
    flagged: list[dict[str, Any]] = []
    for i, s in enumerate(sentences):
        keys = s.get("source_fact_keys") or []
        quote = s.get("quote")
        reasons: list[str] = []
        if not keys:
            reasons.append("missing_source_fact_keys")
        if quote:
            if quote not in report_text and quote.lower() not in report_text.lower():
                reasons.append("quote_not_in_report")
        else:
            # Allow empty quote only if no keys either — still flag
            if keys:
                reasons.append("missing_quote")
        if reasons:
            flagged.append({"index": i, "sentence": s.get("sentence"), "reasons": reasons})
    return {
        "total_sentences": len(sentences),
        "flagged": flagged,
        "unsupported_count": len(flagged),
        "support_rate": ((len(sentences) - len(flagged)) / len(sentences)) if sentences else 1.0,
        "pass": len(flagged) == 0,
    }


def reading_level_check(
    report_text: str,
    explanation: dict[str, Any],
    target_max_grade: float = 8.5,
) -> dict[str, Any]:
    original = flesch_kincaid_grade(report_text)
    expl_text = explanation_text_from_payload(explanation)
    explained = flesch_kincaid_grade(expl_text)
    return {
        "original_grade": original,
        "explanation_grade": explained,
        "delta": round(original - explained, 2),
        "meets_target": explained <= target_max_grade,
        "simpler_than_original": explained < original,
        "target_max_grade": target_max_grade,
    }


def run_all_checks(
    *,
    facts: dict[str, Any],
    explanation: dict[str, Any],
    report_text: str,
    gold_labels: dict[str, Any] | None = None,
    gdc_metadata: dict[str, Any] | None = None,
    cancer_type: str | None = None,
) -> dict[str, Any]:
    """Run the full automatic check suite for one generation."""
    results: dict[str, Any] = {
        "field_accuracy": field_accuracy(facts, gold_labels) if gold_labels else {"scored": False},
        "number_grounding": number_grounding(explanation, report_text, facts),
        "unsupported_sentences": unsupported_sentences(explanation, report_text),
        "reading_level": reading_level_check(report_text, explanation),
    }
    if cancer_type is not None:
        results["tcga_metadata_agreement"] = metadata_agrees_with_report(gdc_metadata, cancer_type)
    return results
