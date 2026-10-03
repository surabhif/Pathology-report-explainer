"""Automatic evaluation check unit tests."""

from __future__ import annotations

from app.services.checks import (
    field_accuracy,
    number_grounding,
    run_all_checks,
    unsupported_sentences,
)
from app.services.llm.mock import build_explanation, extract_facts_heuristic
from app.seed import BRCA_REPORT_1


def test_number_grounding_pass():
    report = "Tumor size 2.5 cm. 2 of 15 lymph nodes positive."
    explanation = {
        "sentences": [
            {
                "sentence": "The tumor is 2.5 cm.",
                "source_fact_keys": ["tumor_size"],
                "quote": "2.5 cm",
            },
            {
                "sentence": "2 of 15 lymph nodes had cancer.",
                "source_fact_keys": ["lymph_nodes_positive", "lymph_nodes_examined"],
                "quote": "2 of 15 lymph nodes",
            },
        ]
    }
    result = number_grounding(explanation, report)
    assert result["pass"] is True
    assert result["ungrounded"] == []


def test_number_grounding_fail_hallucinated_number():
    report = "Tumor size 2.5 cm."
    explanation = {
        "sentences": [
            {
                "sentence": "The tumor is 9.9 cm wide.",
                "source_fact_keys": ["tumor_size"],
                "quote": "2.5 cm",
            }
        ]
    }
    result = number_grounding(explanation, report)
    assert result["pass"] is False
    assert "9.9" in result["ungrounded"]


def test_unsupported_sentences_missing_keys():
    explanation = {
        "sentences": [
            {"sentence": "Something vague.", "source_fact_keys": [], "quote": None},
            {
                "sentence": "Margins are clear.",
                "source_fact_keys": ["margins"],
                "quote": "margins are negative",
            },
        ]
    }
    report = "Surgical margins are negative for invasive carcinoma."
    result = unsupported_sentences(explanation, report)
    assert result["unsupported_count"] >= 1
    assert result["flagged"][0]["index"] == 0


def test_unsupported_sentences_quote_not_in_report():
    explanation = {
        "sentences": [
            {
                "sentence": "Grade is high.",
                "source_fact_keys": ["grade"],
                "quote": "this quote does not exist anywhere",
            }
        ]
    }
    result = unsupported_sentences(explanation, "Grade 2 tumor.")
    assert result["pass"] is False
    assert "quote_not_in_report" in result["flagged"][0]["reasons"]


def test_field_accuracy_match():
    gold = {
        "grade": {"value": "2", "quote": "grade 2", "start_char": 0, "end_char": 7},
        "diagnosis_or_histologic_type": None,
    }
    pred = {
        "grade": {"value": "2", "quote": "Grade 2", "start_char": 0, "end_char": 7},
    }
    result = field_accuracy(pred, gold)
    assert result["total"] == 1
    assert result["correct"] == 1
    assert result["accuracy"] == 1.0


def test_run_all_checks_on_mock_pipeline():
    facts = extract_facts_heuristic(BRCA_REPORT_1)
    explanation = build_explanation(facts)
    results = run_all_checks(
        facts=facts,
        explanation=explanation,
        report_text=BRCA_REPORT_1,
        gold_labels=facts,  # self-agreement
        gdc_metadata={"project_id": "TCGA-BRCA", "found": True},
        cancer_type="BRCA",
    )
    assert results["field_accuracy"]["accuracy"] == 1.0
    assert results["number_grounding"]["pass"] is True
    assert "reading_level" in results
    assert results["tcga_metadata_agreement"]["agreed"] is True
