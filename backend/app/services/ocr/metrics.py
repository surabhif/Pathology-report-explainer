"""Character / word error rates vs a reference transcript (TCGA-Reports / Textract).

Uses rapidfuzz's compiled Levenshtein distance so CER/WER stay off the
critical path of the async event loop (see pipeline + to_thread).
"""

from __future__ import annotations

import re
from typing import Any

from rapidfuzz.distance import Levenshtein

_WS = re.compile(r"\s+")


def normalize_for_cer(text: str) -> str:
    """Light normalization so layout whitespace does not dominate CER."""
    return _WS.sub(" ", (text or "").strip()).lower()


def tokenize_words(text: str) -> list[str]:
    return [t for t in re.split(r"\s+", (text or "").strip().lower()) if t]


def _edit_distance(a: list[str] | str, b: list[str] | str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    return int(Levenshtein.distance(a, b))


def character_error_rate(reference: str, hypothesis: str) -> float:
    ref = normalize_for_cer(reference)
    hyp = normalize_for_cer(hypothesis)
    if not ref:
        return 0.0 if not hyp else 1.0
    return _edit_distance(ref, hyp) / len(ref)


def word_error_rate(reference: str, hypothesis: str) -> float:
    ref = tokenize_words(reference)
    hyp = tokenize_words(hypothesis)
    if not ref:
        return 0.0 if not hyp else 1.0
    return _edit_distance(ref, hyp) / len(ref)


def ocr_error_metrics(reference: str, hypothesis: str) -> dict[str, Any]:
    """Sync CER/WER helper — call via ``asyncio.to_thread`` from async routes."""
    cer = character_error_rate(reference, hypothesis)
    wer = word_error_rate(reference, hypothesis)
    return {
        "cer": round(cer, 4),
        "wer": round(wer, 4),
        "ref_chars": len(normalize_for_cer(reference)),
        "hyp_chars": len(normalize_for_cer(hypothesis)),
        "ref_words": len(tokenize_words(reference)),
        "hyp_words": len(tokenize_words(hypothesis)),
    }


def metrics_from_payload(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    """Reuse CER/WER already stored on a disk/DB OCR payload (avoid recomputing)."""
    if not payload:
        return None
    meta = payload.get("meta") or {}
    cer = payload.get("cer")
    wer = payload.get("wer")
    if cer is None:
        cer = meta.get("cer")
    if wer is None:
        wer = meta.get("wer")
    if cer is None or wer is None:
        return None
    out = {
        "cer": float(cer),
        "wer": float(wer),
        "ref_chars": meta.get("ref_chars"),
        "hyp_chars": meta.get("hyp_chars"),
        "ref_words": meta.get("ref_words"),
        "hyp_words": meta.get("hyp_words"),
    }
    return out


def word_diff_spans(reference: str, hypothesis: str) -> dict[str, Any]:
    """Word-level diff for UI highlighting via rapidfuzz opcodes."""
    ref_tokens = tokenize_words(reference)
    hyp_tokens = tokenize_words(hypothesis)
    ops: list[dict[str, str]] = []
    for tag, i1, i2, j1, j2 in Levenshtein.opcodes(ref_tokens, hyp_tokens):
        if tag == "equal":
            for k in range(i2 - i1):
                ops.append(
                    {
                        "op": "equal",
                        "ref": ref_tokens[i1 + k],
                        "hyp": hyp_tokens[j1 + k],
                    }
                )
        elif tag == "replace":
            # Emit deletes then inserts so the UI can render both sides.
            for k in range(i1, i2):
                ops.append({"op": "delete", "ref": ref_tokens[k], "hyp": ""})
            for k in range(j1, j2):
                ops.append({"op": "insert", "ref": "", "hyp": hyp_tokens[k]})
        elif tag == "delete":
            for k in range(i1, i2):
                ops.append({"op": "delete", "ref": ref_tokens[k], "hyp": ""})
        elif tag == "insert":
            for k in range(j1, j2):
                ops.append({"op": "insert", "ref": "", "hyp": hyp_tokens[k]})
    return {"ops": ops, "changed": sum(1 for o in ops if o["op"] != "equal")}
