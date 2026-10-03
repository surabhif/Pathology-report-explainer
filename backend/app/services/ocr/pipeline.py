"""Run OCR over cached scan pages for a report; cache + tag results.

Public demo serves **precomputed** OCR only (committed under data/ocr_cache/).
Live / forced Tesseract is admin-only and runs off the event loop so /health
keeps answering on Render's free tier.
"""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import OcrRun, Report
from app.services.ocr import OcrPageResult, OcrResult
from app.services.ocr.cache import (
    cache_key_for_pages,
    load_disk_cache,
    ocr_cache_root,
    write_disk_cache,
)
from app.services.ocr.factory import get_ocr_engine
from app.services.ocr.metrics import metrics_from_payload, ocr_error_metrics
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


def find_disk_ocr_payload(barcode: str, engine: str = "tesseract") -> dict[str, Any] | None:
    """Load the newest committed OCR disk-cache payload for a case (no Tesseract)."""
    root = ocr_cache_root() / case_submitter_id(barcode) / engine
    if not root.is_dir():
        return None
    files = sorted(root.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    for path in files:
        data = load_disk_cache(path)
        if data and data.get("text"):
            data = dict(data)
            data.setdefault("meta", {})
            data["meta"] = {
                **(data.get("meta") or {}),
                "disk_cache_path": str(path),
                "precomputed": True,
            }
            return data
    return None


def _metrics_for_text(reference: str, hypothesis: str, payload: dict[str, Any] | None) -> dict[str, Any]:
    reused = metrics_from_payload(payload)
    if reused is not None:
        return reused
    return ocr_error_metrics(reference, hypothesis)


async def _metrics_for_text_async(
    reference: str, hypothesis: str, payload: dict[str, Any] | None
) -> dict[str, Any]:
    reused = metrics_from_payload(payload)
    if reused is not None:
        return reused
    # Compiled rapidfuzz distance — still off the loop so /health stays responsive.
    return await asyncio.to_thread(ocr_error_metrics, reference, hypothesis)


def _persist_from_payload(
    db: Session,
    report: Report,
    payload: dict[str, Any],
    *,
    cache_key: str | None,
    from_disk: bool,
    precomputed: bool,
) -> OcrRun:
    text = payload.get("text") or ""
    ref_metrics = _metrics_for_text(report.report_text, text, payload)
    meta = {
        **(payload.get("meta") or {}),
        "from_disk_cache": from_disk,
        "precomputed": precomputed,
        **{k: v for k, v in ref_metrics.items() if v is not None},
    }
    if precomputed and not meta.get("precomputed_at"):
        # Prefer file mtime encoded by caller; else use now-ish from created_at later.
        meta["precomputed_at"] = meta.get("precomputed_at") or payload.get("precomputed_at")
    run = OcrRun(
        report_id=report.id,
        engine=payload.get("engine") or "unknown",
        engine_version=payload.get("engine_version") or "",
        model=payload.get("model"),
        text=text,
        pages_json=payload.get("pages") or [],
        duration_ms=float(payload.get("duration_ms") or 0),
        estimated_cost_usd=payload.get("estimated_cost_usd"),
        cer=ref_metrics.get("cer"),
        wer=ref_metrics.get("wer"),
        cache_key=cache_key,
        meta_json=meta,
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
    precomputed: bool = False,
) -> OcrRun:
    meta = {**(result.meta or {}), **ref_metrics, "precomputed": precomputed}
    run = OcrRun(
        report_id=report.id,
        engine=result.engine,
        engine_version=result.engine_version,
        model=result.model,
        text=result.text,
        pages_json=result.to_dict()["pages"],
        duration_ms=result.duration_ms,
        estimated_cost_usd=result.estimated_cost_usd,
        cer=ref_metrics.get("cer"),
        wer=ref_metrics.get("wer"),
        cache_key=cache_key,
        meta_json=meta,
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


def ensure_precomputed_ocr_run(
    db: Session,
    report: Report,
    *,
    engine: str = "tesseract",
) -> OcrRun | None:
    """Load committed disk-cache OCR into ``ocr_runs`` (no live Tesseract)."""
    existing = latest_ocr_run(db, report.id, engine=engine)
    if existing and (existing.meta_json or {}).get("precomputed"):
        return existing
    if existing and existing.cer is not None and existing.wer is not None and existing.text:
        # Already have a usable run (e.g. from a prior live job) — keep it.
        return existing

    payload = find_disk_ocr_payload(report.tcga_barcode, engine=engine)
    if not payload:
        return existing

    cache_key = (payload.get("meta") or {}).get("cache_key")
    # Stamp precomputed_at from disk file mtime when available.
    disk_path = (payload.get("meta") or {}).get("disk_cache_path")
    if disk_path:
        try:
            mtime = Path(disk_path).stat().st_mtime
            from datetime import datetime, timezone

            payload["precomputed_at"] = datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()
        except OSError:
            pass

    return _persist_from_payload(
        db,
        report,
        payload,
        cache_key=cache_key,
        from_disk=True,
        precomputed=True,
    )


def get_precomputed_ocr(
    db: Session,
    report: Report,
    *,
    engine: str | None = None,
) -> OcrRun | None:
    """Public path: return precomputed OCR only — never runs Tesseract."""
    settings = get_settings()
    eng = engine or settings.ocr_engine
    run = ensure_precomputed_ocr_run(db, report, engine=eng)
    if run:
        return run
    # Fall back to any engine's precomputed disk cache.
    if eng != "tesseract":
        return ensure_precomputed_ocr_run(db, report, engine="tesseract")
    return None


async def run_ocr_on_report(
    db: Session,
    report: Report,
    *,
    engine_name: str | None = None,
    force: bool = False,
    max_pages: int | None = None,
    allow_live: bool = False,
) -> OcrRun:
    """OCR cached scan pages; persist OcrRun + disk cache; compute CER/WER vs reference.

    ``allow_live=False`` (default): only return precomputed / existing runs.
    Live Tesseract requires ``allow_live=True`` (admin) and respects queue limits.
    """
    settings = get_settings()
    eng_name = engine_name or settings.ocr_engine

    # Non-forced path: always prefer DB / committed disk OCR (never live Tesseract).
    # This keeps public Stage 2 and admin benchmarks off the free-tier CPU path.
    if not force:
        pre = get_precomputed_ocr(db, report, engine=eng_name)
        if pre:
            return pre
        if not allow_live:
            raise FileNotFoundError(
                f"No precomputed OCR for {report.tcga_barcode}. "
                "Public demo serves offline OCR only; admins can run live OCR."
            )

    if not allow_live:
        raise PermissionError("Live OCR is admin-only on this deployment.")

    engine = get_ocr_engine(eng_name)
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
            return _persist_from_payload(
                db, report, disk, cache_key=cache_key, from_disk=True, precomputed=True
            )

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

    ref_metrics = await _metrics_for_text_async(report.report_text, combined, None)
    result = OcrResult(
        engine=eng_id,
        engine_version=eng_ver,
        text=combined,
        pages=page_results,
        duration_ms=total_ms,
        estimated_cost_usd=est_cost,
        model=model,
        meta={"cache_key": cache_key, "page_count": len(page_results), "precomputed": False, **ref_metrics},
    )
    payload = result.to_dict()
    # Persist CER/WER at top-level too so later loads never recompute.
    payload["cer"] = ref_metrics.get("cer")
    payload["wer"] = ref_metrics.get("wer")
    write_disk_cache(disk_path, payload)
    return _persist_result(
        db, report, result, cache_key=cache_key, ref_metrics=ref_metrics, precomputed=False
    )
