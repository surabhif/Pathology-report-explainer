"""Schema validation tests for FactSheet / extraction output."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas import ExplanationPayload, FactSheet
from app.services.extraction import validate_facts
from app.services.llm.mock import extract_facts_heuristic
from app.seed import BRCA_REPORT_1


def test_fact_sheet_accepts_null_fields():
    sheet = FactSheet()
    dumped = sheet.model_dump()
    assert dumped["diagnosis_or_histologic_type"] is None
    assert dumped["biomarkers"] is None


def test_fact_sheet_valid_span():
    sheet = validate_facts(
        {
            "diagnosis_or_histologic_type": {
                "value": "Invasive ductal carcinoma",
                "quote": "Invasive ductal carcinoma",
                "start_char": 0,
                "end_char": 26,
            },
            "grade": None,
            "tumor_size": None,
            "margins": None,
            "lymph_nodes_positive": None,
            "lymph_nodes_examined": None,
            "pathologic_tnm_stage": None,
            "biomarkers": None,
        }
    )
    assert sheet.diagnosis_or_histologic_type is not None
    assert sheet.diagnosis_or_histologic_type.value == "Invasive ductal carcinoma"


def test_fact_sheet_rejects_bad_span_type():
    with pytest.raises(ValidationError):
        FactSheet.model_validate(
            {
                "grade": "not-an-object",
            }
        )


def test_mock_extraction_produces_valid_schema():
    raw = extract_facts_heuristic(BRCA_REPORT_1)
    sheet = validate_facts(raw)
    assert sheet.diagnosis_or_histologic_type is not None
    assert "ductal" in str(sheet.diagnosis_or_histologic_type.value).lower()
    assert sheet.tumor_size is not None
    assert sheet.lymph_nodes_positive is not None
    assert sheet.lymph_nodes_positive.value == 2
    assert sheet.lymph_nodes_examined is not None
    assert sheet.lymph_nodes_examined.value == 15
    assert sheet.pathologic_tnm_stage is not None
    assert sheet.biomarkers is not None
    assert isinstance(sheet.biomarkers.value, dict)


def test_explanation_payload_schema():
    payload = ExplanationPayload.model_validate(
        {
            "sentences": [
                {
                    "sentence": "The tumor measures about 2.5 cm.",
                    "source_fact_keys": ["tumor_size"],
                    "quote": "2.5 cm",
                }
            ]
        }
    )
    assert len(payload.sentences) == 1
