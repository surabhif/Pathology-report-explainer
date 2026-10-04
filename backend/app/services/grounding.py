"""Quote / sentence grounding helpers.

A sentence is grounded only when it has a non-empty quote whose *normalized*
form appears in the source report. Normalization: lowercase, collapse
whitespace, strip punctuation. Matching is still exact on the normalized
token stream (not fuzzy/semantic).

Ellipsis-stitched quotes (``pT3 ... N0``) are split into pieces; every piece
must match. Original character offsets are recovered so UI highlight can land
on the real report span (e.g. ``free of. tumor``).
"""

from __future__ import annotations

import re
import string
from typing import Any

_WS = re.compile(r"\s+")
_ELLIPSIS = re.compile(r"(?:\.{3}|…)")
_PUNCT_TABLE = str.maketrans({c: " " for c in string.punctuation})


def normalize_quote(quote: Any) -> str:
    if quote is None:
        return ""
    return str(quote).strip()


def normalize_for_grounding(text: str) -> str:
    """Lowercase, strip punctuation to spaces, collapse whitespace."""
    if not text:
        return ""
    lowered = text.lower().translate(_PUNCT_TABLE)
    return _WS.sub(" ", lowered).strip()


def split_ellipsis_quote(quote: str) -> list[str]:
    """Split a quote on ``...`` / ``…`` into non-empty pieces."""
    q = normalize_quote(quote)
    if not q:
        return []
    parts = [p.strip() for p in _ELLIPSIS.split(q) if p.strip()]
    return parts or [q]


def _normalized_with_index_map(text: str) -> tuple[str, list[int]]:
    """Return normalized text plus map: norm_index → original char index.

    Each normalized character (including spaces inserted for punctuation /
    collapsed whitespace) maps to the *first* original character that produced
    it, so span ends can be recovered as the start of the next mapped char.
    """
    norm_chars: list[str] = []
    index_map: list[int] = []
    prev_space = True  # strip leading space
    for i, ch in enumerate(text):
        low = ch.lower()
        if low in string.punctuation:
            # Punctuation becomes a single space (collapsed with neighbors).
            if not prev_space and norm_chars:
                norm_chars.append(" ")
                index_map.append(i)
                prev_space = True
            continue
        if low.isspace():
            if not prev_space and norm_chars:
                norm_chars.append(" ")
                index_map.append(i)
                prev_space = True
            continue
        norm_chars.append(low)
        index_map.append(i)
        prev_space = False
    # Trim trailing space
    if norm_chars and norm_chars[-1] == " ":
        norm_chars.pop()
        index_map.pop()
    return "".join(norm_chars), index_map


def _find_single_span(quote: str, report_text: str) -> tuple[int, int] | None:
    """Locate one contiguous quote piece in ``report_text``."""
    q = normalize_quote(quote)
    if not q or not report_text:
        return None
    # Fast path: exact / case-insensitive contiguous match.
    idx = report_text.find(q)
    if idx >= 0:
        return idx, idx + len(q)
    idx = report_text.lower().find(q.lower())
    if idx >= 0:
        return idx, idx + len(q)

    norm_report, index_map = _normalized_with_index_map(report_text)
    norm_quote = normalize_for_grounding(q)
    if not norm_quote or not norm_report:
        return None
    pos = norm_report.find(norm_quote)
    if pos < 0:
        return None
    start = index_map[pos]
    end_pos = pos + len(norm_quote) - 1
    last_orig = index_map[end_pos]
    return start, last_orig + 1


def find_quote_span(quote: str, report_text: str) -> tuple[int, int] | None:
    """Locate ``quote`` in ``report_text`` after grounding normalization.

    Ellipsis-stitched quotes are accepted when every piece matches. Highlight
    span uses the first matching piece so the UI lands on real report text.
    Returns ``(start, end)`` offsets into the *original* report text, or None.
    """
    parts = split_ellipsis_quote(quote)
    if not parts:
        return None
    spans: list[tuple[int, int]] = []
    for part in parts:
        span = _find_single_span(part, report_text)
        if span is None:
            return None
        spans.append(span)
    return spans[0]


def quote_found_in_report(quote: str, report_text: str) -> bool:
    """True when normalized ``quote`` (or every ellipsis piece) is found."""
    return find_quote_span(quote, report_text) is not None


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
        grounding: dict[str, Any] = {"ok": len(reasons) == 0, "reasons": reasons}
        quote = normalize_quote(item.get("quote"))
        if quote:
            span = find_quote_span(quote, report_text)
            if span:
                grounding["start_char"] = span[0]
                grounding["end_char"] = span[1]
        item["grounding"] = grounding
        if not quote:
            item["quote"] = None
        sentences_out.append(item)
    return {**explanation, "sentences": sentences_out}
