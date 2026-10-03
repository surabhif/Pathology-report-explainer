"""Quote / sentence grounding helpers.

A sentence is grounded only when it has a non-empty quote that appears
word-for-word (contiguous substring, case-insensitive) in the source report.
Empty quotes and invented paraphrases are unsupported — never display them
as if they were evidence-backed.
"""

from __future__ import annotations

from typing import Any


def normalize_quote(quote: Any) -> str:
    if quote is None:
        return ""
    return str(quote).strip()


def quote_found_in_report(quote: str, report_text: str) -> bool:
    """True when ``quote`` appears as a contiguous substring of the report.

    Matching is case-insensitive so OCR casing quirks do not false-flag a
    real span; the words themselves must still match exactly in order.
    """
    q = normalize_quote(quote)
    if not q or not report_text:
        return False
    if q in report_text:
        return True
    return q.lower() in report_text.lower()


def assess_sentence_grounding(sentence: dict[str, Any], report_text: str) -> list[str]:
    """Return reason codes when a sentence is not fully grounded; empty if OK."""
    reasons: list[str] = []
    keys = sentence.get("source_fact_keys") or []
    quote = normalize_quote(sentence.get("quote"))

    if not keys:
        reasons.append("missing_source_fact_keys")
    if not quote:
        reasons.append("missing_quote")
    elif not quote_found_in_report(quote, report_text):
        reasons.append("quote_not_in_report")
    return reasons


def annotate_explanation_grounding(
    explanation: dict[str, Any],
    report_text: str,
) -> dict[str, Any]:
    """Return a copy of explanation JSON with per-sentence grounding metadata."""
    sentences_out: list[dict[str, Any]] = []
    for s in explanation.get("sentences") or []:
        item = dict(s)
        reasons = assess_sentence_grounding(item, report_text)
        item["grounding"] = {"ok": len(reasons) == 0, "reasons": reasons}
        # Normalize empty/whitespace quotes to null for honest storage.
        if not normalize_quote(item.get("quote")):
            item["quote"] = None
        sentences_out.append(item)
    return {**explanation, "sentences": sentences_out}
