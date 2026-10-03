"""Run OCR over cached scan pages for a report; cache + tag results."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import OcrRun, Report
from app.services.ocr import OcrPageResult, OcrResult
from app.services.ocr.cache import cache_key_for_pages, load_disk_cache, write_disk_cache
from app.services.ocr.factory import get_ocr_engine
from app.services.ocr.metrics import ocr_error_metrics
from app.services.ocr.xai_vision import DEFAULT_EST_USD_PER_PAGE_HIGH, DEFAULT_EST_USD_PER_PAGE_LOW
from app.services.scan_assets import case_cache_dir, case_submitter_id, is_real_scan_manifest, load_manifest

logger = logging.getLogger(__name__)


def _page_paths_for_report(report: Report) -> list[Path]:
    manifest = report.scan_manifest or load_manifest(report.tcga_barcode) or {}
    if not is_real_scan_manifest(manifest):
        raise FileNotFoundError(
            f"No real scan pages for {report.tcga_barcode} "
            f"(source={manifest.get('source')!r}). Facsimiles are not OCR'd for scoring."
        )
    pages = manifest.get("pages") or []
    root = case_cache_dir(report.tcga_barcode)
    paths: list[Path] = []
    for p in pages:
        filename = p.get("filename")
        if not filename:
            continue
        path = root / filename
        if path.exists():
            paths.append(path)
    return paths


async def run_ocr_on_report(
    db: Session,
    report: Report,
    *,
    engine_name: str | None = None,
    force: bool = False,
    max_pages: int | None = None,
) -> OcrRun:
    """OCR cached scan pages; persist OcrRun + disk cache; compute CER/WER vs reference."""
    settings = get_settings()
    engine = get_ocr_engine(engine_name)
    eng_id = engine.engine_id()
    eng_ver = engine.engine_version()
    limit = max_pages if max_pages is not None else settings.ocr_max_pages

    paths = _page_paths_for_report(report)[: max(1, limit)]
    if not paths:
        raise FileNotFoundError(
            f"No cached scan pages for {report.tcga_barcode}. "
            "Run fetch_scan_pages.py first."
        )

    image_bytes_list = [p.read_bytes() for p in paths]
    cache_key, disk_path = cache_key_for_pages(
        case_submitter_id(report.tcga_barcode),
        eng_id,
        eng_ver,
        image_bytes_list,
    )

    if not force:
        existing = (
            db.query(OcrRun)
            .filter(
                OcrRun.report_id == report.id,
                OcrRun.engine == eng_id,
                OcrRun.engine_version == eng_ver,
                OcrRun.cache_key == cache_key,
            )
            .order_by(OcrRun.id.desc())
            .first()
        )
        if existing:
            return existing
        disk = load_disk_cache(disk_path)
        if disk and disk.get("text") is not None:
            return _persist_from_payload(db, report, disk, cache_key=cache_key, from_disk=True)

    t0 = time.perf_counter()
    page_results: list[OcrPageResult] = []
    for idx, (path, blob) in enumerate(zip(paths, image_bytes_list), start=1):
        mime = "image/jpeg" if path.suffix.lower() in {".jpg", ".jpeg"} else "image/png"
        page_res = await engine.ocr_image_bytes(blob, mime=mime, page=idx)
        page_res.filename = path.name
        page_results.append(page_res)

    combined = "\n\n".join(p.text for p in page_results if p.text).strip()
    total_ms = (time.perf_counter() - t0) * 1000

    est_cost: float | None = None
    model: str | None = None
    if eng_id == "xai_vision":
        detail = settings.ocr_vision_detail
        per = DEFAULT_EST_USD_PER_PAGE_HIGH if detail == "high" else DEFAULT_EST_USD_PER_PAGE_LOW
        est_cost = round(per * len(page_results), 6)
        model = getattr(engine, "_model", None)

    ref_metrics = ocr_error_metrics(report.report_text, combined)
    result = OcrResult(
        engine=eng_id,
        engine_version=eng_ver,
        text=combined,
        pages=page_results,
        duration_ms=total_ms,
        estimated_cost_usd=est_cost,
        model=model,
        meta={"cache_key": cache_key, "page_count": len(page_results), **ref_metrics},
    )
    payload = result.to_dict()
    write_disk_cache(disk_path, payload)
    return _persist_result(db, report, result, cache_key=cache_key, ref_metrics=ref_metrics)


def _persist_from_payload(
    db: Session,
    report: Report,
    payload: dict[str, Any],
    *,
    cache_key: str,
    from_disk: bool,
) -> OcrRun:
    text = payload.get("text") or ""
    ref_metrics = ocr_error_metrics(report.report_text, text)
    run = OcrRun(
        report_id=report.id,
        engine=payload.get("engine") or "unknown",
        engine_version=payload.get("engine_version") or "",
        model=payload.get("model"),
        text=text,
        pages_json=payload.get("pages") or [],
        duration_ms=float(payload.get("duration_ms") or 0),
        estimated_cost_usd=payload.get("estimated_cost_usd"),
        cer=ref_metrics["cer"],
        wer=ref_metrics["wer"],
        cache_key=cache_key,
        meta_json={**(payload.get("meta") or {}), "from_disk_cache": from_disk, **ref_metrics},
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def _persist_result(
    db: Session,
    report: Report,
    result: OcrResult,
    *,
    cache_key: str,
    ref_metrics: dict[str, Any],
) -> OcrRun:
    run = OcrRun(
        report_id=report.id,
        engine=result.engine,
        engine_version=result.engine_version,
        model=result.model,
        text=result.text,
        pages_json=result.to_dict()["pages"],
        duration_ms=result.duration_ms,
        estimated_cost_usd=result.estimated_cost_usd,
        cer=ref_metrics["cer"],
        wer=ref_metrics["wer"],
        cache_key=cache_key,
        meta_json=result.meta,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def latest_ocr_run(db: Session, report_id: int, engine: str | None = None) -> OcrRun | None:
    q = db.query(OcrRun).filter(OcrRun.report_id == report_id)
    if engine:
        q = q.filter(OcrRun.engine == engine)
    return q.order_by(OcrRun.id.desc()).first()
