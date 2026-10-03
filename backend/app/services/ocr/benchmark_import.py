"""Import the committed real-scan OCR benchmark into ``ocr_benchmark_runs``."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import OcrBenchmarkRun, Report

logger = logging.getLogger(__name__)

SEEDED_FROM = "ocr_benchmark_latest.json"


def default_benchmark_path() -> Path:
    return Path(get_settings().data_dir) / "ocr_benchmark_latest.json"


def find_seeded_benchmark(db: Session) -> OcrBenchmarkRun | None:
    for row in db.query(OcrBenchmarkRun).order_by(OcrBenchmarkRun.id.desc()).all():
        summary = (row.results_json or {}).get("summary") or {}
        if summary.get("seeded_from") == SEEDED_FROM:
            return row
    return None


def import_ocr_benchmark_from_json(
    db: Session,
    path: Path | None = None,
    *,
    force: bool = False,
) -> OcrBenchmarkRun:
    """Load ``ocr_benchmark_latest.json`` and remap barcodes → current report ids.

    Facsimile rows are dropped. Idempotent unless ``force=True`` (then inserts a
    new row so Results picks it up as latest).
    """
    if not force:
        existing = find_seeded_benchmark(db)
        if existing:
            return existing

    src = path or default_benchmark_path()
    if not src.is_file():
        raise FileNotFoundError(f"OCR benchmark file missing: {src}")

    payload = json.loads(src.read_text(encoding="utf-8"))
    summary = dict(payload.get("summary") or {})
    per_report_in = list(payload.get("per_report") or [])

    barcode_to_id = {
        r.tcga_barcode: r.id for r in db.query(Report).all() if r.tcga_barcode
    }
    per_report: list[dict[str, Any]] = []
    report_ids: list[int] = []
    n_facsimile = 0
    for row in per_report_in:
        source = row.get("scan_source")
        if source == "ocr_text_facsimile" or row.get("excluded_reason") == (
            "facsimile_circular_vs_textract_reference"
        ):
            n_facsimile += 1
            continue
        if row.get("scored") is False and not row.get("cer"):
            # Keep unscored non-facsimile rows out of the seeded board.
            continue
        bc = row.get("tcga_barcode")
        rid = barcode_to_id.get(bc) if bc else None
        if rid is None:
            continue
        new_row = {**row, "report_id": rid}
        per_report.append(new_row)
        if rid not in report_ids:
            report_ids.append(rid)

    summary["seeded_from"] = SEEDED_FROM
    summary["n_facsimile_excluded"] = int(summary.get("n_facsimile_excluded") or 0) + n_facsimile
    summary["n_real_scans_scored"] = sum(1 for r in per_report if r.get("scored"))
    if "integrity_note" not in summary:
        summary["integrity_note"] = (
            "CER/WER are computed only on authentic page images (Tatonetti Textract "
            "inputs or GDC PDF renders). OCR-text facsimiles are excluded."
        )

    engine = payload.get("engine") or summary.get("engine") or "tesseract"
    engine_version = (
        payload.get("engine_version") or summary.get("engine_version") or "tesseract-5.3.4"
    )
    run = OcrBenchmarkRun(
        engine=engine,
        engine_version=engine_version,
        report_ids=report_ids or payload.get("report_ids") or [],
        results_json={"per_report": per_report, "summary": summary},
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    logger.info(
        "ocr.benchmark.imported id=%s n_real=%s path=%s",
        run.id,
        summary.get("n_real_scans_scored"),
        src.name,
    )
    return run


def ensure_ocr_benchmark_seeded(db: Session) -> OcrBenchmarkRun | None:
    """Idempotent: import committed benchmark if not already present."""
    try:
        return import_ocr_benchmark_from_json(db, force=False)
    except FileNotFoundError:
        logger.warning("ocr.benchmark.seed_skipped missing %s", default_benchmark_path())
        return None
