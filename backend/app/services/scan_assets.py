"""Locate, download, and cache TCGA pathology-report scan page images.

Primary source: NCI GDC public API
  - data_category: Clinical
  - data_type: Pathology Report
  - data_format: PDF
  Download: https://api.gdc.cancer.gov/data/{file_id}

Fallback for packaging when GDC is unreachable: a clearly labeled page
facsimile rendered from the open OCR text (TCGA-Reports / Textract). The
facsimile is ONLY for demo layout — never presented as a GDC scan.

Tatonetti lab page images (imgs_for_aws.zip, ~24GB) are the Textract inputs
from Kefeli et al.; too large to pull for MVP. Prefer GDC PDFs.
"""

from __future__ import annotations

import io
import json
import logging
import re
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)

GDC_FILES_URL = "https://api.gdc.cancer.gov/files"
GDC_DATA_URL = "https://api.gdc.cancer.gov/data"

OCR_CITATION = (
    "Kefeli et al., TCGA-Reports (Patterns 2024) — machine-readable text via AWS Textract"
)


def case_submitter_id(barcode: str) -> str:
    """TCGA-XX-XXXX from a longer aliquot barcode."""
    parts = barcode.strip().split("-")
    if len(parts) >= 3 and parts[0].upper() == "TCGA":
        return f"TCGA-{parts[1]}-{parts[2]}"
    return barcode.strip()


def scan_cache_root() -> Path:
    """Repo data/scan_cache — committed demo pages live here."""
    # backend/app/services → backend → repo
    return Path(__file__).resolve().parents[3] / "data" / "scan_cache"


def case_cache_dir(barcode: str) -> Path:
    return scan_cache_root() / case_submitter_id(barcode)


def manifest_path(barcode: str) -> Path:
    return case_cache_dir(barcode) / "manifest.json"


def load_manifest(barcode: str) -> dict[str, Any] | None:
    path = manifest_path(barcode)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def write_manifest(barcode: str, manifest: dict[str, Any]) -> Path:
    d = case_cache_dir(barcode)
    d.mkdir(parents=True, exist_ok=True)
    path = d / "manifest.json"
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return path


async def find_gdc_pathology_pdf(barcode: str, timeout: float = 45.0) -> dict[str, Any] | None:
    """Return the first open-access Pathology Report PDF file hit for a case."""
    submitter = case_submitter_id(barcode)
    filters = {
        "op": "and",
        "content": [
            {"op": "in", "content": {"field": "cases.submitter_id", "value": [submitter]}},
            {"op": "in", "content": {"field": "data_category", "value": ["Clinical"]}},
            {"op": "in", "content": {"field": "data_type", "value": ["Pathology Report"]}},
            {"op": "in", "content": {"field": "data_format", "value": ["PDF"]}},
        ],
    }
    payload = {
        "filters": filters,
        "fields": "file_id,file_name,file_size,access,data_format,data_type,data_category",
        "format": "JSON",
        "size": 5,
    }
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(GDC_FILES_URL, json=payload)
        resp.raise_for_status()
        data = resp.json()
    hits = data.get("data", {}).get("hits") or []
    if not hits:
        logger.info("gdc.pathology_pdf.none submitter=%s", submitter)
        return None
    # Prefer open access
    hits_sorted = sorted(hits, key=lambda h: 0 if h.get("access") == "open" else 1)
    hit = hits_sorted[0]
    logger.info(
        "gdc.pathology_pdf.hit submitter=%s file_id=%s name=%s",
        submitter,
        hit.get("file_id"),
        hit.get("file_name"),
    )
    return hit


async def download_gdc_file(file_id: str, dest: Path, timeout: float = 120.0) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    url = f"{GDC_DATA_URL}/{file_id}"
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        async with client.stream("GET", url) as resp:
            resp.raise_for_status()
            with dest.open("wb") as f:
                async for chunk in resp.aiter_bytes():
                    f.write(chunk)
    return dest


def render_pdf_pages(
    pdf_path: Path,
    out_dir: Path,
    *,
    max_pages: int = 2,
    zoom: float = 1.5,
) -> list[dict[str, Any]]:
    """Render the first pages of a PDF to JPEG with PyMuPDF."""
    import pymupdf  # type: ignore

    out_dir.mkdir(parents=True, exist_ok=True)
    doc = pymupdf.open(pdf_path)
    pages: list[dict[str, Any]] = []
    try:
        n = min(len(doc), max_pages)
        mat = pymupdf.Matrix(zoom, zoom)
        for i in range(n):
            page = doc[i]
            pix = page.get_pixmap(matrix=mat, alpha=False)
            name = f"page-{i + 1:02d}.jpg"
            path = out_dir / name
            pix.save(str(path), output="jpeg", jpg_quality=82)
            pages.append(
                {
                    "page": i + 1,
                    "filename": name,
                    "width": pix.width,
                    "height": pix.height,
                    "relpath": f"{out_dir.name}/{name}",
                }
            )
    finally:
        doc.close()
    return pages


def render_ocr_facsimile_pages(
    report_text: str,
    out_dir: Path,
    *,
    max_pages: int = 2,
    barcode: str = "",
) -> list[dict[str, Any]]:
    """Render OCR text onto paper-like page images for demo layout only.

    Manifest must set source=ocr_text_facsimile so the UI never claims these
    are authentic GDC scans.
    """
    from PIL import Image, ImageDraw, ImageFont

    out_dir.mkdir(parents=True, exist_ok=True)
    # Letter-ish page at ~110 dpi equivalent for small cache size
    W, H = 850, 1100
    margin = 48
    line_h = 18
    chars_per_line = 88

    # Word-wrap OCR text into page chunks
    words = re.split(r"(\s+)", report_text.replace("\r\n", "\n"))
    lines: list[str] = []
    cur = ""
    for w in words:
        if w == "\n":
            lines.append(cur.rstrip())
            cur = ""
            continue
        if len(cur) + len(w) > chars_per_line:
            lines.append(cur.rstrip())
            cur = w.lstrip() if w.strip() else ""
        else:
            cur += w
    if cur.strip():
        lines.append(cur.rstrip())

    lines_per_page = max(10, (H - 2 * margin - 80) // line_h)
    chunks = [lines[i : i + lines_per_page] for i in range(0, len(lines), lines_per_page)]
    chunks = chunks[:max_pages] or [["(empty report)"]]

    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 13)
        font_sm = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 11)
        font_hdr = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 14)
    except OSError:
        font = ImageFont.load_default()
        font_sm = font
        font_hdr = font

    pages: list[dict[str, Any]] = []
    for i, chunk in enumerate(chunks):
        img = Image.new("RGB", (W, H), (236, 232, 223))
        draw = ImageDraw.Draw(img)
        # subtle paper edge
        draw.rectangle([12, 12, W - 13, H - 13], outline=(190, 180, 160), width=2)
        header = f"TCGA pathology report  ·  {barcode or 'sample'}  ·  page {i + 1}"
        draw.text((margin, 22), header, fill=(60, 55, 45), font=font_hdr)
        draw.text(
            (margin, 42),
            "FACSIMILE from OCR text — not a GDC scan page (replace via fetch_scan_pages.py)",
            fill=(140, 60, 40),
            font=font_sm,
        )
        y = margin + 40
        for line in chunk:
            draw.text((margin, y), line[:chars_per_line], fill=(35, 32, 28), font=font)
            y += line_h
            if y > H - margin:
                break
        name = f"page-{i + 1:02d}.jpg"
        path = out_dir / name
        img.save(path, format="JPEG", quality=80, optimize=True)
        pages.append(
            {
                "page": i + 1,
                "filename": name,
                "width": W,
                "height": H,
                "relpath": f"{out_dir.name}/{name}",
            }
        )
    return pages


async def ensure_scan_pages_for_barcode(
    barcode: str,
    report_text: str,
    *,
    allow_facsimile: bool = True,
    max_pages: int = 2,
    force: bool = False,
) -> dict[str, Any]:
    """Fetch GDC PDF pages or fall back to OCR facsimile; write manifest."""
    submitter = case_submitter_id(barcode)
    out_dir = case_cache_dir(barcode)
    existing = load_manifest(barcode)
    if existing and not force and existing.get("pages"):
        return existing

    out_dir.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, Any] = {
        "barcode": barcode,
        "case_submitter_id": submitter,
        "pages": [],
        "source": None,
        "label": None,
        "citation": None,
        "gdc_file_id": None,
        "gdc_file_name": None,
    }

    try:
        hit = await find_gdc_pathology_pdf(barcode)
        if hit and hit.get("file_id"):
            pdf_path = out_dir / "pathology_report.pdf"
            await download_gdc_file(hit["file_id"], pdf_path)
            pages = render_pdf_pages(pdf_path, out_dir, max_pages=max_pages)
            # Prefer relative paths under case dir for serving
            for p in pages:
                p["relpath"] = f"{submitter}/{p['filename']}"
            manifest.update(
                {
                    "pages": pages,
                    "source": "gdc_pdf",
                    "label": "Original scanned pathology report (NCI GDC PDF page render)",
                    "citation": (
                        "Open-access TCGA pathology report PDF from the NCI Genomic Data Commons "
                        "(Clinical / Pathology Report / PDF)."
                    ),
                    "gdc_file_id": hit.get("file_id"),
                    "gdc_file_name": hit.get("file_name"),
                }
            )
            write_manifest(barcode, manifest)
            return manifest
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "gdc.scan_fetch_failed barcode=%s err=%s",
            barcode,
            type(exc).__name__,
        )
        manifest["gdc_error"] = type(exc).__name__

    if not allow_facsimile:
        write_manifest(barcode, manifest)
        return manifest

    pages = render_ocr_facsimile_pages(report_text, out_dir, max_pages=max_pages, barcode=submitter)
    for p in pages:
        p["relpath"] = f"{submitter}/{p['filename']}"
    manifest.update(
        {
            "pages": pages,
            "source": "ocr_text_facsimile",
            "label": "Page facsimile from OCR text (GDC scan not cached)",
            "citation": (
                "Authentic open-access scans are TCGA pathology report PDFs on the NCI GDC. "
                "GDC was unreachable or returned no PDF during caching, so this demo shows a "
                "layout facsimile rendered from the publicly released TCGA-Reports OCR text. "
                "Re-run scripts/fetch_scan_pages.py when GDC is available to replace these images."
            ),
            "ocr_attribution": OCR_CITATION,
        }
    )
    write_manifest(barcode, manifest)
    return manifest
