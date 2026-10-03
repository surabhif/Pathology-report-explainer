"""Aggregate metrics with 95% confidence intervals.

Uses Wilson score interval for proportions (recommended for accuracy rates)
and normal approximation for means when n is larger.
"""

from __future__ import annotations

import csv
import io
import math
from typing import Any, Iterable


def wilson_interval(successes: int, n: int, z: float = 1.96) -> tuple[float, float, float]:
    """Wilson score 95% CI for a binomial proportion.

    Returns (proportion, ci_low, ci_high).
    """
    if n <= 0:
        return 0.0, 0.0, 0.0
    p = successes / n
    z2 = z * z
    denom = 1 + z2 / n
    center = (p + z2 / (2 * n)) / denom
    margin = (z / denom) * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n))
    low = max(0.0, center - margin)
    high = min(1.0, center + margin)
    return p, low, high


def normal_mean_ci(values: list[float], z: float = 1.96) -> tuple[float, float, float]:
    """Normal-approx 95% CI for the mean."""
    n = len(values)
    if n == 0:
        return 0.0, 0.0, 0.0
    mean = sum(values) / n
    if n == 1:
        return mean, mean, mean
    var = sum((x - mean) ** 2 for x in values) / (n - 1)
    se = math.sqrt(var / n)
    return mean, mean - z * se, mean + z * se


def metric_dict(name: str, value: float, n: int, ci_low: float, ci_high: float, method: str) -> dict[str, Any]:
    return {
        "name": name,
        "value": round(value, 4),
        "n": n,
        "ci_low": round(ci_low, 4),
        "ci_high": round(ci_high, 4),
        "method": method,
    }


def proportion_metric(name: str, successes: int, n: int) -> dict[str, Any]:
    p, low, high = wilson_interval(successes, n)
    return metric_dict(name, p, n, low, high, "wilson")


def mean_metric(name: str, values: list[float]) -> dict[str, Any]:
    m, low, high = normal_mean_ci(values)
    return metric_dict(name, m, len(values), low, high, "normal")


def summarize_check_results(runs: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Aggregate a list of per-generation check result dicts into metrics with CIs."""
    runs = list(runs)
    metrics: list[dict[str, Any]] = []

    # Field accuracy (micro-average over scored fields)
    acc_success = 0
    acc_total = 0
    for r in runs:
        fa = r.get("field_accuracy") or {}
        if fa.get("total"):
            acc_success += fa.get("correct", 0)
            acc_total += fa["total"]
    if acc_total:
        metrics.append(proportion_metric("field_accuracy", acc_success, acc_total))

    # Number grounding pass rate
    ng_pass = sum(1 for r in runs if (r.get("number_grounding") or {}).get("pass"))
    if runs:
        metrics.append(proportion_metric("number_grounding_pass_rate", ng_pass, len(runs)))

    # Unsupported sentence support rate (mean of support_rate)
    support_rates = [
        (r.get("unsupported_sentences") or {}).get("support_rate")
        for r in runs
        if (r.get("unsupported_sentences") or {}).get("support_rate") is not None
    ]
    if support_rates:
        metrics.append(mean_metric("sentence_support_rate", support_rates))

    # Reading level
    expl_grades = [
        (r.get("reading_level") or {}).get("explanation_grade")
        for r in runs
        if (r.get("reading_level") or {}).get("explanation_grade") is not None
    ]
    if expl_grades:
        metrics.append(mean_metric("explanation_reading_grade", expl_grades))
        meet = sum(
            1
            for r in runs
            if (r.get("reading_level") or {}).get("meets_target")
        )
        metrics.append(proportion_metric("reading_level_meets_target", meet, len(runs)))

    # TCGA agreement
    agreed = 0
    checked = 0
    for r in runs:
        t = r.get("tcga_metadata_agreement") or {}
        if t.get("checked") and t.get("agreed") is not None:
            checked += 1
            if t.get("agreed"):
                agreed += 1
    if checked:
        metrics.append(proportion_metric("tcga_metadata_agreement", agreed, checked))

    return metrics


def inter_rater_agreement(
    reviews_by_item: dict[Any, list[dict[str, Any]]],
    score_keys: tuple[str, ...] = ("accuracy", "completeness", "harm_potential"),
) -> dict[str, Any]:
    """Pairwise exact-agreement rate when ≥2 clinicians review the same item.

    ``reviews_by_item`` maps generation_id (or any item key) → list of score dicts.
    Returns proportion of pairwise dimension comparisons that match exactly,
    plus n_items_with_multiple_raters and n_pairs. Empty when insufficient dual reviews.
    """
    exact = 0
    total = 0
    n_multi = 0
    n_pairs = 0
    for _item, score_list in reviews_by_item.items():
        if len(score_list) < 2:
            continue
        n_multi += 1
        for i in range(len(score_list)):
            for j in range(i + 1, len(score_list)):
                n_pairs += 1
                a, b = score_list[i], score_list[j]
                for key in score_keys:
                    if a.get(key) is None or b.get(key) is None:
                        continue
                    total += 1
                    if a.get(key) == b.get(key):
                        exact += 1
    if total == 0:
        return {
            "available": False,
            "n_items_with_multiple_raters": n_multi,
            "n_pairs": n_pairs,
            "metric": None,
        }
    return {
        "available": True,
        "n_items_with_multiple_raters": n_multi,
        "n_pairs": n_pairs,
        "metric": proportion_metric("inter_rater_exact_agreement", exact, total),
    }


def results_to_csv(rows: list[dict[str, Any]]) -> str:
    """Serialize metric rows (and optional detail rows) to CSV string."""
    buf = io.StringIO()
    if not rows:
        return ""
    # Union of keys for stable header
    fieldnames: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for k in row:
            if k not in seen:
                seen.add(k)
                fieldnames.append(k)
    writer = csv.DictWriter(buf, fieldnames=fieldnames)
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return buf.getvalue()
