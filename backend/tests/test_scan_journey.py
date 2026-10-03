"""Tests for scan page caching and the public report journey API."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app.services.scan_assets import (
    case_submitter_id,
    ensure_scan_pages_for_barcode,
    load_manifest,
    render_ocr_facsimile_pages,
    scan_cache_root,
)


def test_case_submitter_id_truncates_aliquot():
    assert case_submitter_id("TCGA-B6-A401-01A-11-TS1") == "TCGA-B6-A401"
    assert case_submitter_id("TCGA-B6-A401") == "TCGA-B6-A401"


def test_render_ocr_facsimile_writes_jpeg(tmp_path: Path):
    pages = render_ocr_facsimile_pages(
        "FINAL DIAGNOSIS: Invasive ductal carcinoma.\nTumor size: 2.1 cm.",
        tmp_path,
        max_pages=1,
        barcode="TCGA-TEST-0001",
    )
    assert len(pages) == 1
    assert pages[0]["filename"] == "page-01.jpg"
    assert (tmp_path / "page-01.jpg").exists()
    assert (tmp_path / "page-01.jpg").stat().st_size > 500


@pytest.mark.asyncio
async def test_ensure_scan_pages_facsimile_when_gdc_missing(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        "app.services.scan_assets.scan_cache_root",
        lambda: tmp_path / "scan_cache",
    )
    with patch(
        "app.services.scan_assets.find_gdc_pathology_pdf",
        new=AsyncMock(return_value=None),
    ):
        manifest = await ensure_scan_pages_for_barcode(
            "TCGA-XX-9999",
            "Histologic type: adenocarcinoma. Nodes: 0/12.",
            allow_facsimile=True,
            force=True,
        )
    assert manifest["source"] == "ocr_text_facsimile"
    assert manifest["pages"]
    assert "Textract" in (manifest.get("ocr_attribution") or "")
    assert load_manifest("TCGA-XX-9999") is not None
    page = tmp_path / "scan_cache" / "TCGA-XX-9999" / "page-01.jpg"
    assert page.exists()


@pytest.mark.asyncio
async def test_journey_endpoint_attributes_ocr_to_tcga_reports(client):
    reports = (await client.get("/api/public/reports?cancer_type=BRCA")).json()
    assert reports, "seed should include BRCA samples"
    rid = reports[0]["id"]
    journey = (await client.get(f"/api/public/reports/{rid}/journey")).json()
    assert journey["report_id"] == rid
    assert "Textract" in journey["ocr_label"]
    assert "TCGA-Reports" in journey["ocr_label"] or "Kefeli" in journey["ocr_citation"]
    assert journey["report_text"]
    assert journey["explain_path"].endswith(f"/reports/{rid}/explain")
    assert journey.get("default_ocr_engine")


@pytest.mark.asyncio
async def test_explain_includes_journey_and_serves_cached_pages(client):
    reports = (await client.get("/api/public/reports?cancer_type=BRCA")).json()
    rid = reports[0]["id"]
    barcode = reports[0]["tcga_barcode"]

    expl = (await client.get(f"/api/public/reports/{rid}/explain")).json()
    assert expl["journey"] is not None
    assert "Textract" in expl["journey"]["ocr_label"]
    assert "reference" in expl["journey"]["ocr_label"].lower() or "Kefeli" in expl["journey"]["ocr_citation"]

    # Demo samples ship scan_cache pages; seed attaches the manifest.
    pages = expl["journey"]["scan_pages"]
    assert pages, f"expected cached pages for {barcode}"
    assert expl["journey"]["scan_source"] in {"gdc_pdf", "ocr_text_facsimile"}

    url = pages[0]["url"]
    assert f"/api/public/reports/{rid}/scan-pages/" in url
    img = await client.get(url)
    assert img.status_code == 200
    assert img.headers["content-type"].startswith("image/")
    assert len(img.content) > 500


@pytest.mark.asyncio
async def test_scan_page_rejects_path_traversal(client):
    reports = (await client.get("/api/public/reports")).json()
    rid = reports[0]["id"]
    # Filename param cannot contain "/" (router won't match); block ".." substrings.
    dotted = await client.get(f"/api/public/reports/{rid}/scan-pages/..page-01.jpg")
    assert dotted.status_code == 400


def test_committed_demo_scan_cache_present():
    """Demo samples ship page images under data/scan_cache (not hot-linked)."""
    root = scan_cache_root()
    assert root.is_dir()
    for barcode in ("TCGA-B6-A401", "TCGA-A6-3808", "TCGA-44-8119"):
        manifest = load_manifest(barcode)
        assert manifest is not None, barcode
        assert manifest.get("pages"), barcode
        for page in manifest["pages"]:
            assert (root / barcode / page["filename"]).exists()
