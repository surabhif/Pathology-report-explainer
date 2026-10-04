"""Metrics / confidence-interval math tests."""

from __future__ import annotations

import math

from app.services.metrics import (
    inter_rater_agreement,
    mean_metric,
    normal_mean_ci,
    proportion_metric,
    summarize_check_results,
    wilson_interval,
)


def test_wilson_interval_known_values():
    # Classic: 8/10 successes — CI should be within (0,1) and contain p
    p, low, high = wilson_interval(8, 10)
    assert abs(p - 0.8) < 1e-9
    assert 0.0 <= low < p < high <= 1.0
    # Wilson is slightly asymmetric; rough expected low ~0.49, high ~0.94
    assert low < 0.6
    assert high > 0.9


def test_wilson_interval_zero_n():
    p, low, high = wilson_interval(0, 0)
    assert (p, low, high) == (0.0, 0.0, 0.0)


def test_wilson_interval_all_success():
    p, low, high = wilson_interval(10, 10)
    assert p == 1.0
    assert low < 1.0  # still has uncertainty
    assert high == 1.0


def test_normal_mean_ci():
    values = [1.0, 2.0, 3.0, 4.0, 5.0]
    mean, low, high = normal_mean_ci(values)
    assert abs(mean - 3.0) < 1e-9
    assert low < mean < high
    # SE of mean for this sample: s/sqrt(n); s = sqrt(2.5) ≈ 1.581
    se = math.sqrt(2.5 / 5)
    assert abs((mean - low) - 1.96 * se) < 1e-6


def test_proportion_metric_shape():
    m = proportion_metric("accuracy", 7, 10)
    assert m["name"] == "accuracy"
    assert m["method"] == "wilson"
    assert m["n"] == 10
    assert m["ci_low"] <= m["value"] <= m["ci_high"]


def test_mean_metric_shape():
    m = mean_metric("grade", [6.0, 7.0, 8.0])
    assert m["method"] == "normal"
    assert m["n"] == 3


def test_summarize_check_results():
    runs = [
        {
            "field_accuracy": {"correct": 4, "total": 5, "accuracy": 0.8},
            "number_grounding": {"pass": True},
            "unsupported_sentences": {"support_rate": 1.0},
            "reading_level": {"explanation_grade": 7.0, "meets_target": True},
            "tcga_metadata_agreement": {"checked": True, "agreed": True},
        },
        {
            "field_accuracy": {"correct": 3, "total": 5, "accuracy": 0.6},
            "number_grounding": {"pass": False},
            "unsupported_sentences": {"support_rate": 0.5},
            "reading_level": {"explanation_grade": 9.0, "meets_target": False},
            "tcga_metadata_agreement": {"checked": True, "agreed": True},
        },
    ]
    metrics = summarize_check_results(runs)
    names = {m["name"] for m in metrics}
    assert "field_accuracy" in names
    assert "number_grounding_pass_rate" in names
    assert "tcga_metadata_agreement" in names
    fa = next(m for m in metrics if m["name"] == "field_accuracy")
    assert fa["n"] == 10
    assert abs(fa["value"] - 0.7) < 1e-6


def test_inter_rater_agreement():
    by_item = {
        1: [
            {"accuracy": 4, "completeness": 5, "harm_potential": 2},
            {"accuracy": 4, "completeness": 4, "harm_potential": 2},
        ],
        2: [{"accuracy": 3, "completeness": 3, "harm_potential": 3}],  # single rater — ignored
    }
    out = inter_rater_agreement(by_item)
    assert out["available"] is True
    assert out["n_items_with_multiple_raters"] == 1
    assert out["n_pairs"] == 1
    # 2 of 3 dimensions match exactly
    assert abs(out["metric"]["value"] - (2 / 3)) < 1e-3


def test_inter_rater_insufficient():
    out = inter_rater_agreement({1: [{"accuracy": 5, "completeness": 5, "harm_potential": 1}]})
    assert out["available"] is False
    assert out["metric"] is None
