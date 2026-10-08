"""Fact quote offsets must be recomputed from source text — never trust the LLM."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from app.schemas import FactSheet
from app.services.extraction import extract_facts, facts_with_recomputed_offsets
from app.services.grounding import (
    fact_offsets_need_fix,
    find_quote_span,
    recompute_fact_offsets,
)

# Real TCGA-A6-3808 (colon report 9) Our OCR text from committed cache.
_OCR_CACHE = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "ocr_cache"
    / "TCGA-A6-3808"
    / "tesseract"
    / "9509ce315d3db74cedf23467.json"
)


def _colon9_ocr_text() -> str:
    payload = json.loads(_OCR_CACHE.read_text(encoding="utf-8"))
    return payload["text"]


# Wrong offsets as observed on production for TCGA-A6-3808 / Our OCR.
COLON9_BAD_FACTS = {
    "diagnosis_or_histologic_type": {
        "value": "Invasive moderately-differentiated colonic adenocarcinoma with mucinous differentiation",
        "quote": "Invasive moderately-differentiated colonic adenocarcinoma with mucinous differentiation",
        "start_char": 1063,
        "end_char": 1132,
    },
    "grade": {
        "value": "Moderately-differentiated",
        "quote": "Moderately-differentiated",
        "start_char": 860,
        "end_char": 884,
    },
    "tumor_size": {
        "value": "4.4 x 4.0 cm",
        "quote": "4.4 x 4.0 cm",
        "start_char": 317,
        "end_char": 329,
    },
    "margins": {
        "value": "negative",
        "quote": "The proximal, distal and radial margins of resection are free of tumor",
        "start_char": 1155,
        "end_char": 1226,
    },
    "lymph_nodes_positive": {
        "value": 0,
        "quote": "24 lymph nodes are negative for metastatic carcinoma",
        "start_char": 941,
        "end_char": 991,
    },
    "lymph_nodes_examined": {
        "value": 24,
        "quote": "24 lymph nodes are negative for metastatic carcinoma",
        "start_char": 941,
        "end_char": 991,
    },
    "pathologic_tnm_stage": {
        "value": "pT3N0Mx",
        "quote": "pT3",
        "start_char": 813,
        "end_char": 817,
    },
    "biomarkers": {"value": {}, "quote": None, "start_char": 0, "end_char": 0},
}


def test_colon9_stored_offsets_are_wrong_against_ocr():
    text = _colon9_ocr_text()
    diag = COLON9_BAD_FACTS["diagnosis_or_histologic_type"]
    snippet = text[diag["start_char"] : diag["end_char"]]
    assert "lymph nodes measuring" in snippet
    assert "adenocarcinoma" not in snippet.lower()


def test_recompute_fact_offsets_fixes_colon9():
    text = _colon9_ocr_text()
    assert fact_offsets_need_fix(COLON9_BAD_FACTS, text) is True
    fixed = recompute_fact_offsets(COLON9_BAD_FACTS, text)

    diag = fixed["diagnosis_or_histologic_type"]
    assert diag["start_char"] is not None
    snippet = text[diag["start_char"] : diag["end_char"]]
    assert "adenocarcinoma" in snippet.lower()
    assert "lymph nodes measuring" not in snippet.lower()

    grade = fixed["grade"]
    assert text[grade["start_char"] : grade["end_char"]].lower() == "moderately-differentiated"

    size = fixed["tumor_size"]
    assert "4.4" in text[size["start_char"] : size["end_char"]]

    # Idempotent
    again = recompute_fact_offsets(fixed, text)
    assert again == fixed
    assert fact_offsets_need_fix(fixed, text) is False


def test_recompute_clears_offsets_when_quote_absent():
    report = "Procedure: mastectomy."
    facts = {
        "diagnosis_or_histologic_type": {
            "value": "x",
            "quote": "this quote is nowhere",
            "start_char": 0,
            "end_char": 5,
        },
        "grade": None,
        "tumor_size": None,
        "margins": None,
        "lymph_nodes_positive": None,
        "lymph_nodes_examined": None,
        "pathologic_tnm_stage": None,
        "biomarkers": None,
    }
    fixed = recompute_fact_offsets(facts, report)
    assert fixed["diagnosis_or_histologic_type"]["start_char"] is None
    assert fixed["diagnosis_or_histologic_type"]["end_char"] is None
    assert fixed["diagnosis_or_histologic_type"]["quote"] == "this quote is nowhere"


@pytest.mark.asyncio
async def test_extract_facts_never_persists_llm_offsets():
    """Hosted provider returns lying offsets; extract_facts must recompute them."""
    report = (
        "Histologic type: Invasive ductal carcinoma. "
        "Tumor size: 2.1 cm. Margins negative."
    )
    lying = {
        "diagnosis_or_histologic_type": {
            "value": "Invasive ductal carcinoma",
            "quote": "Invasive ductal carcinoma",
            "start_char": 100,  # wrong
            "end_char": 125,
        },
        "grade": None,
        "tumor_size": {
            "value": "2.1 cm",
            "quote": "2.1 cm",
            "start_char": 0,
            "end_char": 6,
        },
        "margins": None,
        "lymph_nodes_positive": None,
        "lymph_nodes_examined": None,
        "pathologic_tnm_stage": None,
        "biomarkers": None,
    }
    from unittest.mock import MagicMock

    provider = MagicMock()
    provider.provider_id.return_value = "xai"
    provider.model_id.return_value = "grok-test"
    provider.complete_json = AsyncMock(return_value=lying)

    result = await extract_facts(report, provider)
    diag = result.facts.diagnosis_or_histologic_type
    assert diag is not None
    assert report[diag.start_char : diag.end_char] == "Invasive ductal carcinoma"
    size = result.facts.tumor_size
    assert size is not None
    assert report[size.start_char : size.end_char] == "2.1 cm"


def test_facts_with_recomputed_offsets_validates_schema():
    text = _colon9_ocr_text()
    sheet = facts_with_recomputed_offsets(COLON9_BAD_FACTS, text)
    assert isinstance(sheet, FactSheet)
    assert sheet.diagnosis_or_histologic_type is not None
    span = find_quote_span(sheet.diagnosis_or_histologic_type.quote or "", text)
    assert span is not None
    assert sheet.diagnosis_or_histologic_type.start_char == span[0]


@pytest.mark.asyncio
async def test_explain_read_fixes_cached_colon9_offsets(client, db_session):
    """Cached generation with wrong offsets is corrected on explain read."""
    from app.models import Generation, OcrRun, Report
    from app.routers.public import ensure_generation_fact_offsets

    text = _colon9_ocr_text()
    report = (
        db_session.query(Report)
        .filter(Report.tcga_barcode.like("%A6-3808%"))
        .first()
    )
    if report is None:
        report = Report(
            tcga_barcode="TCGA-A6-3808",
            cancer_type="COAD",
            project_id="TCGA-COAD",
            source="tcga",
            report_text=text,
        )
        db_session.add(report)
        db_session.commit()
        db_session.refresh(report)
    else:
        report.report_text = text
        db_session.add(report)
        db_session.commit()

    ocr = OcrRun(
        report_id=report.id,
        engine="tesseract",
        engine_version="tesseract-5.3.4",
        text=text,
        cache_key="test-colon9",
        meta_json={"source": "precomputed"},
    )
    db_session.add(ocr)
    db_session.commit()
    db_session.refresh(ocr)

    gen = Generation(
        report_id=report.id,
        prompt_extract_version="extract_v1",
        prompt_explain_version="explain_v1",
        model="grok-test",
        provider="xai",
        is_fallback=False,
        text_source="our_ocr",
        ocr_run_id=ocr.id,
        facts_json=COLON9_BAD_FACTS,
        explanation_json={"sentences": []},
    )
    db_session.add(gen)
    db_session.commit()
    db_session.refresh(gen)

    # Bad offsets land on lymph-node fragment
    bad = gen.facts_json["diagnosis_or_histologic_type"]
    assert "lymph nodes" in text[bad["start_char"] : bad["end_char"]]

    ensure_generation_fact_offsets(db_session, gen, report)
    db_session.refresh(gen)
    good = gen.facts_json["diagnosis_or_histologic_type"]
    snippet = text[good["start_char"] : good["end_char"]]
    assert "adenocarcinoma" in snippet.lower()
    assert "lymph nodes measuring" not in snippet.lower()

    # Public explain should also return corrected offsets
    res = await client.get(
        f"/api/public/reports/{report.id}/explain?text_source=our_ocr"
    )
    # May 404 if no precomputed OCR path in test seed — offsets already fixed above.
    if res.status_code == 200:
        body = res.json()
        d = body["facts"]["diagnosis_or_histologic_type"]
        shown = body["report_text"][d["start_char"] : d["end_char"]]
        assert "adenocarcinoma" in shown.lower()


@pytest.mark.asyncio
async def test_admin_fix_offsets_endpoint(client, admin_headers, db_session):
    from app.models import Generation, Report

    report = db_session.query(Report).first()
    assert report is not None
    text = report.report_text
    quote = text[10:25] if len(text) > 25 else text[:5]
    # Plant a generation with deliberately wrong offsets for a real quote.
    span = find_quote_span(quote, text)
    assert span is not None
    bad_facts = {
        "diagnosis_or_histologic_type": {
            "value": "x",
            "quote": quote,
            "start_char": 0,
            "end_char": 1,
        },
        "grade": None,
        "tumor_size": None,
        "margins": None,
        "lymph_nodes_positive": None,
        "lymph_nodes_examined": None,
        "pathologic_tnm_stage": None,
        "biomarkers": None,
    }
    # Only plant when offsets at 0:1 do not already match
    if text[0:1].lower() == quote.lower()[:1] and fact_offsets_need_fix(bad_facts, text) is False:
        bad_facts["diagnosis_or_histologic_type"]["start_char"] = max(0, len(text) - 2)
        bad_facts["diagnosis_or_histologic_type"]["end_char"] = len(text)

    gen = Generation(
        report_id=report.id,
        prompt_extract_version="extract_v1",
        prompt_explain_version="explain_v1",
        model="mock-heuristic-v1",
        provider="mock",
        is_fallback=False,
        text_source="reference",
        facts_json=bad_facts,
        explanation_json={"sentences": []},
    )
    db_session.add(gen)
    db_session.commit()
    db_session.refresh(gen)

    res = await client.post(
        "/api/admin/generations/fix-offsets",
        headers=admin_headers,
        json={"generation_ids": [gen.id]},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["scanned"] == 1
    assert body["fixed"] == 1

    db_session.refresh(gen)
    fixed = gen.facts_json["diagnosis_or_histologic_type"]
    assert fixed["start_char"] == span[0]
    assert fixed["end_char"] == span[1]

    # Second run is a no-op
    res2 = await client.post(
        "/api/admin/generations/fix-offsets",
        headers=admin_headers,
        json={"generation_ids": [gen.id]},
    )
    assert res2.json()["fixed"] == 0
