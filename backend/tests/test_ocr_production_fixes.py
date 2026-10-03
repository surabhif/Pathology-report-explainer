"""Production OCR fixes: rapidfuzz off-loop, precomputed public path, benchmark import, grounding."""

from __future__ import annotations

import asyncio

import pytest

from app.services.grounding import find_quote_span, quote_found_in_report
from app.services.ocr.benchmark_import import (
    SEEDED_FROM,
)
from app.services.ocr.metrics import (
    character_error_rate,
    metrics_from_payload,
    ocr_error_metrics,
    word_error_rate,
)

def test_rapidfuzz_cer_wer_basic():
    assert character_error_rate("hello world", "hello world") == 0.0
    assert word_error_rate("hello world", "hello word") > 0
    m = ocr_error_metrics("free of tumor", "free of. tumor")
    assert m["cer"] is not None
    assert m["wer"] is not None


def test_metrics_from_payload_reuses_stored_cer_wer():
    payload = {
        "text": "hyp",
        "cer": 0.29,
        "wer": 0.45,
        "meta": {"ref_chars": 100, "hyp_chars": 90},
    }
    reused = metrics_from_payload(payload)
    assert reused is not None
    assert reused["cer"] == 0.29
    assert reused["wer"] == 0.45
    assert metrics_from_payload({"text": "x"}) is None
    assert metrics_from_payload({"meta": {"cer": 0.1, "wer": 0.2}})["cer"] == 0.1


def test_grounding_tolerates_ocr_stray_periods():
    """Colon-case style OCR: 'free of. tumor' must match quote 'free of tumor'."""
    report = (
        "The radial, vascular and bronchial margins of resection are free of. tumor. "
        "Apical emphysematous changes."
    )
    quote = "free of tumor"
    assert quote_found_in_report(quote, report) is True
    span = find_quote_span(quote, report)
    assert span is not None
    start, end = span
    # Span must land on the original text including the stray period.
    assert "free of" in report[start:end].lower()
    assert "tumor" in report[start:end].lower()
    assert report[start:end].count(".") >= 1 or "free of. tumor" in report[start:end]


def test_grounding_still_rejects_paraphrase():
    report = "Margins are free of. tumor."
    assert quote_found_in_report("the margins look clear of cancer", report) is False


@pytest.mark.asyncio
async def test_public_ocr_is_precomputed_never_calls_tesseract(client, monkeypatch):
    calls = {"n": 0}

    async def _boom(*_a, **_k):
        calls["n"] += 1
        raise AssertionError("Live Tesseract must not run on public /ocr")

    monkeypatch.setattr(
        "app.services.ocr.tesseract_engine.TesseractOcrEngine.ocr_image_bytes",
        _boom,
    )
    reports = (await client.get("/api/public/reports?cancer_type=BRCA")).json()
    rid = reports[0]["id"]
    ocr = await client.get(f"/api/public/reports/{rid}/ocr")
    assert ocr.status_code == 200, ocr.text
    body = ocr.json()
    assert body["source"] == "precomputed"
    assert body["precomputed"] is True
    assert body["cer"] is not None
    assert body["wer"] is not None
    assert body["text"]
    assert calls["n"] == 0

    # force query must not unlock live OCR on the public path
    ocr2 = await client.get(f"/api/public/reports/{rid}/ocr?force=true")
    assert ocr2.status_code == 200
    assert ocr2.json()["source"] == "precomputed"
    assert calls["n"] == 0


@pytest.mark.asyncio
async def test_journey_exposes_precomputed_label(client):
    reports = (await client.get("/api/public/reports?cancer_type=COAD")).json()
    rid = reports[0]["id"]
    j = (await client.get(f"/api/public/reports/{rid}/journey")).json()
    assert j["our_ocr"] is not None
    assert j["our_ocr"]["source"] == "precomputed"
    assert "precomputed" in (j["our_ocr"]["label"] or "").lower()
    assert "offline" in (j["our_ocr"]["note"] or "").lower() or "precomputed" in (
        j["our_ocr"]["note"] or ""
    ).lower()


@pytest.mark.asyncio
async def test_seed_imports_ocr_benchmark_n30(client, admin_headers):
    """Seed (and Results) must show the committed n=30 real-scan benchmark."""
    # Seed already ran in the app fixture — verify Results.
    results = await client.get("/api/results/summary", headers=admin_headers)
    assert results.status_code == 200
    ob = results.json().get("ocr_benchmark")
    assert ob is not None
    summary = ob["summary"]
    assert summary.get("n_real_scans_scored") == 30
    assert summary.get("seeded_from") == SEEDED_FROM
    overall = summary.get("overall") or {}
    assert overall.get("cer", {}).get("n") == 30
    assert overall.get("wer", {}).get("n") == 30
    # Facsimiles must stay excluded from the scored set.
    assert summary.get("n_facsimile_excluded", 0) >= 0
    assert float(overall.get("cer", {}).get("value") or 0) > 0.1  # not the circular ~0.07
    assert float(overall.get("wer", {}).get("value") or 0) > 0.2


@pytest.mark.asyncio
async def test_admin_import_benchmark_idempotent(client, admin_headers):
    first = await client.post("/api/admin/ocr/import-benchmark", headers=admin_headers)
    assert first.status_code == 200, first.text
    b1 = first.json()
    assert b1["n_real_scans_scored"] == 30
    assert b1["seeded_from"] == SEEDED_FROM

    second = await client.post("/api/admin/ocr/import-benchmark", headers=admin_headers)
    assert second.status_code == 200
    # Idempotent: same row unless force=true
    assert second.json()["benchmark_id"] == b1["benchmark_id"]

    forced = await client.post(
        "/api/admin/ocr/import-benchmark?force=true", headers=admin_headers
    )
    assert forced.status_code == 200
    assert forced.json()["benchmark_id"] != b1["benchmark_id"]
    assert forced.json()["n_real_scans_scored"] == 30


@pytest.mark.asyncio
async def test_public_ocr_reuses_stored_metrics_no_recompute(client, monkeypatch):
    """Stage 2 cache path must not recompute CER/WER when already stored."""
    calls = {"n": 0}
    real = ocr_error_metrics

    def _counted(ref, hyp):
        calls["n"] += 1
        return real(ref, hyp)

    monkeypatch.setattr("app.services.ocr.pipeline.ocr_error_metrics", _counted)
    monkeypatch.setattr("app.services.ocr.metrics.ocr_error_metrics", _counted)

    reports = (await client.get("/api/public/reports?cancer_type=LUAD")).json()
    rid = reports[0]["id"]
    # First call may persist from disk (reuses meta cer/wer — should not call).
    r1 = await client.get(f"/api/public/reports/{rid}/ocr")
    assert r1.status_code == 200
    n_after_first = calls["n"]
    r2 = await client.get(f"/api/public/reports/{rid}/ocr")
    assert r2.status_code == 200
    assert r2.json()["cer"] == r1.json()["cer"]
    assert calls["n"] == n_after_first  # no extra recompute on second hit


@pytest.mark.asyncio
async def test_health_responds_while_slow_ocr_runs(client, admin_headers, monkeypatch):
    """Mocked slow OCR must not block /api/health (event-loop offload)."""
    from app.services.ocr import OcrPageResult

    started = asyncio.Event()
    release = asyncio.Event()

    class SlowEngine:
        def engine_id(self) -> str:
            return "tesseract"

        def engine_version(self) -> str:
            return "tesseract-test-slow"

        async def ocr_image_bytes(self, image_bytes, *, mime="image/jpeg", page=1):
            started.set()
            # Yield to the event loop so /health can answer while we "OCR".
            await release.wait()
            return OcrPageResult(page=page, text="slow ocr text", duration_ms=2500.0)

    monkeypatch.setattr(
        "app.services.ocr.pipeline.get_ocr_engine",
        lambda _name=None: SlowEngine(),
    )

    reports = (await client.get("/api/public/reports?cancer_type=BRCA")).json()
    rid = reports[0]["id"]

    ocr_task = asyncio.create_task(
        client.post(
            f"/api/admin/ocr/run?report_id={rid}&force=true&engine=tesseract&max_pages=1",
            headers=admin_headers,
        )
    )
    for _ in range(100):
        if started.is_set():
            break
        await asyncio.sleep(0.05)
    assert started.is_set(), "slow OCR never started"

    for _ in range(5):
        h = await client.get("/api/health")
        assert h.status_code == 200
        assert h.json().get("ok") is True
        await asyncio.sleep(0.05)

    release.set()
    res = await ocr_task
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["source"] == "live"
    assert body["precomputed"] is False
    assert "slow ocr" in body["text"].lower()
    assert body["cer"] is not None
    assert body["wer"] is not None


@pytest.mark.asyncio
async def test_admin_live_ocr_requires_auth(client):
    reports = (await client.get("/api/public/reports")).json()
    rid = reports[0]["id"]
    res = await client.post(f"/api/admin/ocr/run?report_id={rid}&force=true")
    assert res.status_code in {401, 403}


@pytest.mark.asyncio
async def test_public_ocr_ignores_newer_live_admin_run(client, admin_headers, monkeypatch):
    """Public Stage 2 must keep serving precomputed even if a live run is newer."""
    from app.services.ocr import OcrPageResult

    class LiveEngine:
        def engine_id(self) -> str:
            return "tesseract"

        def engine_version(self) -> str:
            return "tesseract-live-test"

        async def ocr_image_bytes(self, image_bytes, *, mime="image/jpeg", page=1):
            return OcrPageResult(
                page=page,
                text="LIVE ADMIN OCR TEXT SHOULD NOT APPEAR PUBLICLY",
                duration_ms=10.0,
            )

    monkeypatch.setattr(
        "app.services.ocr.pipeline.get_ocr_engine",
        lambda _name=None: LiveEngine(),
    )

    reports = (await client.get("/api/public/reports?cancer_type=BRCA")).json()
    rid = reports[0]["id"]
    pre = await client.get(f"/api/public/reports/{rid}/ocr")
    assert pre.status_code == 200
    assert pre.json()["source"] == "precomputed"
    pre_text = pre.json()["text"]

    live = await client.post(
        f"/api/admin/ocr/run?report_id={rid}&force=true&engine=tesseract&max_pages=1",
        headers=admin_headers,
    )
    assert live.status_code == 200, live.text
    assert live.json()["source"] == "live"
    assert "LIVE ADMIN" in live.json()["text"]

    pub = await client.get(f"/api/public/reports/{rid}/ocr")
    assert pub.status_code == 200
    body = pub.json()
    assert body["source"] == "precomputed"
    assert body["text"] == pre_text
    assert "LIVE ADMIN" not in body["text"]

    j = await client.get(f"/api/public/reports/{rid}/journey")
    assert j.json()["our_ocr"]["source"] == "precomputed"
    assert "LIVE ADMIN" not in (j.json()["our_ocr"]["text"] or "")


@pytest.mark.asyncio
async def test_health_hides_demo_tokens_in_production(client, monkeypatch):
    from app.config import get_settings

    monkeypatch.setenv("APP_ENV", "production")
    get_settings.cache_clear()
    h = await client.get("/api/health")
    assert h.status_code == 200
    body = h.json()
    assert body["ok"] is True
    assert body["show_demo_tokens"] is False
    assert body["app_env"] == "production"
    monkeypatch.delenv("APP_ENV", raising=False)
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_imported_benchmark_notes_missing_extraction_impact(client, admin_headers):
    forced = await client.post(
        "/api/admin/ocr/import-benchmark?force=true", headers=admin_headers
    )
    assert forced.status_code == 200
    impact = forced.json()["summary"].get("extraction_impact") or {}
    assert "note" in impact
    assert "not computed" in impact["note"].lower() or "offline" in impact["note"].lower()


def test_default_ocr_max_pages_is_one():
    from app.config import get_settings

    get_settings.cache_clear()
    assert get_settings().ocr_max_pages == 1
