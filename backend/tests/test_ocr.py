"""OCR engines, CER/WER, and public OCR/journey endpoints."""

from __future__ import annotations

import pytest

from app.services.ocr.metrics import character_error_rate, ocr_error_metrics, word_error_rate, word_diff_spans
from app.services.ocr.mock_engine import MockOcrEngine
from app.services.ocr.tesseract_engine import TesseractOcrEngine
from app.services.ocr.factory import get_ocr_engine, tesseract_available


def test_cer_wer_identical():
    assert character_error_rate("Hello World", "hello world") == 0.0
    assert word_error_rate("Hello World", "hello world") == 0.0


def test_cer_wer_detects_errors():
    m = ocr_error_metrics("invasive ductal carcinoma", "invasive ductal carinoma")
    assert m["cer"] > 0
    assert m["wer"] > 0
    assert m["ref_words"] == 3


def test_word_diff_marks_changes():
    diff = word_diff_spans("alpha beta gamma", "alpha beta delta")
    ops = {o["op"] for o in diff["ops"]}
    assert "equal" in ops
    assert diff["changed"] >= 1


@pytest.mark.asyncio
async def test_mock_ocr_engine():
    eng = MockOcrEngine(canned_text="FINAL DIAGNOSIS")
    page = await eng.ocr_image_bytes(b"fake", page=1)
    assert page.text == "FINAL DIAGNOSIS"
    assert eng.engine_id() == "mock"


@pytest.mark.asyncio
async def test_tesseract_on_demo_page_if_available():
    if not tesseract_available():
        pytest.skip("tesseract not installed")
    from pathlib import Path

    path = Path(__file__).resolve().parents[2] / "data" / "scan_cache" / "TCGA-B6-A401" / "page-01.jpg"
    if not path.exists():
        # repo-root data/
        path = Path(__file__).resolve().parents[3] / "data" / "scan_cache" / "TCGA-B6-A401" / "page-01.jpg"
    assert path.exists()
    eng = TesseractOcrEngine()
    page = await eng.ocr_image_bytes(path.read_bytes(), page=1)
    assert len(page.text) > 50
    assert "tesseract" in eng.engine_version()


def test_factory_default_tesseract_or_mock():
    eng = get_ocr_engine("tesseract")
    assert eng.engine_id() in {"tesseract", "mock"}


@pytest.mark.asyncio
async def test_public_ocr_and_diff(client):
    reports = (await client.get("/api/public/reports?cancer_type=BRCA")).json()
    rid = reports[0]["id"]
    ocr = await client.get(f"/api/public/reports/{rid}/ocr?engine=tesseract")
    assert ocr.status_code == 200, ocr.text
    body = ocr.json()
    assert body["engine"] in {"tesseract", "mock"}
    assert body["engine_version"]
    assert body["text"]
    assert body["cer"] is not None
    assert body["wer"] is not None
    assert body["duration_ms"] is not None

    diff = await client.get(f"/api/public/reports/{rid}/ocr/diff")
    assert diff.status_code == 200
    d = diff.json()
    assert "ops" in d
    assert d["cer"] is not None

    # Explain grounded in our OCR
    expl = await client.get(f"/api/public/reports/{rid}/explain?text_source=our_ocr")
    assert expl.status_code == 200
    ej = expl.json()
    assert ej["text_source"] == "our_ocr"
    assert ej["ocr_run_id"] == body["id"]
    assert ej["journey"]["our_ocr"] is not None
    assert "Textract" in ej["journey"]["ocr_label"] or "TCGA-Reports" in ej["journey"]["ocr_label"]


@pytest.mark.asyncio
async def test_admin_ocr_benchmark(client, admin_headers):
    res = await client.post("/api/admin/ocr/benchmark?engine=tesseract", headers=admin_headers)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["benchmark_id"]
    assert body["n_reports"] >= 1
    summary = body["summary"]
    assert summary.get("overall")

    results = await client.get("/api/results/summary", headers=admin_headers)
    assert results.status_code == 200
    assert results.json().get("ocr_benchmark") is not None


@pytest.mark.asyncio
async def test_admin_upload_requires_ack(client, admin_headers):
    files = {"file": ("page.jpg", b"\xff\xd8\xff\xd9", "image/jpeg")}
    res = await client.post(
        "/api/admin/ocr/upload-test",
        headers=admin_headers,
        files=files,
        data={"acknowledge_deidentified": "false"},
    )
    assert res.status_code == 400
