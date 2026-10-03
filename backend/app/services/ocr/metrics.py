"""Character / word error rates vs a reference transcript (TCGA-Reports / Textract)."""

from __future__ import annotations

import re
from typing import Any


def _levenshtein(a: list[str] | str, b: list[str] | str) -> int:
    """Classic DP edit distance (works for chars or tokens)."""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    # Ensure we iterate over sequences
    n, m = len(a), len(b)
    prev = list(range(m + 1))
    for i, ca in enumerate(a, start=1):
        cur = [i] + [0] * m
        for j, cb in enumerate(b, start=1):
            cost = 0 if ca == cb else 1
            cur[j] = min(
                prev[j] + 1,  # delete
                cur[j - 1] + 1,  # insert
                prev[j - 1] + cost,  # substitute
            )
        prev = cur
    return prev[m]


_WS = re.compile(r"\s+")


def normalize_for_cer(text: str) -> str:
    """Light normalization so layout whitespace does not dominate CER."""
    return _WS.sub(" ", (text or "").strip()).lower()


def tokenize_words(text: str) -> list[str]:
    return [t for t in re.split(r"\s+", (text or "").strip().lower()) if t]


def character_error_rate(reference: str, hypothesis: str) -> float:
    ref = normalize_for_cer(reference)
    hyp = normalize_for_cer(hypothesis)
    if not ref:
        return 0.0 if not hyp else 1.0
    return _levenshtein(ref, hyp) / len(ref)


def word_error_rate(reference: str, hypothesis: str) -> float:
    ref = tokenize_words(reference)
    hyp = tokenize_words(hypothesis)
    if not ref:
        return 0.0 if not hyp else 1.0
    return _levenshtein(ref, hyp) / len(ref)


def ocr_error_metrics(reference: str, hypothesis: str) -> dict[str, Any]:
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


def word_diff_spans(reference: str, hypothesis: str) -> dict[str, Any]:
    """Simple word-level diff for UI highlighting (Myers-ish via LCS tokens)."""
    ref_tokens = tokenize_words(reference)
    hyp_tokens = tokenize_words(hypothesis)
    # LCS DP for alignment
    n, m = len(ref_tokens), len(hyp_tokens)
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            if ref_tokens[i - 1] == hyp_tokens[j - 1]:
                dp[i][j] = dp[i - 1][j - 1] + 1
            else:
                dp[i][j] = max(dp[i - 1][j], dp[i][j - 1])
    # Backtrack
    ops: list[dict[str, str]] = []
    i, j = n, m
    stack: list[dict[str, str]] = []
    while i > 0 or j > 0:
        if i > 0 and j > 0 and ref_tokens[i - 1] == hyp_tokens[j - 1]:
            stack.append({"op": "equal", "ref": ref_tokens[i - 1], "hyp": hyp_tokens[j - 1]})
            i -= 1
            j -= 1
        elif j > 0 and (i == 0 or dp[i][j - 1] >= dp[i - 1][j]):
            stack.append({"op": "insert", "ref": "", "hyp": hyp_tokens[j - 1]})
            j -= 1
        else:
            stack.append({"op": "delete", "ref": ref_tokens[i - 1], "hyp": ""})
            i -= 1
    ops = list(reversed(stack))
    return {"ops": ops, "changed": sum(1 for o in ops if o["op"] != "equal")}
