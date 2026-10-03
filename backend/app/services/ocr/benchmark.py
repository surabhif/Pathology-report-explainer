"""OCR benchmark vs TCGA-Reports (Textract) reference + extraction impact.

IMPORTANT: Only real scan pages (Tatonetti Textract inputs or GDC PDF renders)
are scored. OCR-text facsimiles are circular vs the Textract reference and are
excluded — the dashboard reports how many real scans were scored.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any

from sqlalchemy.orm import Session

from app.models import AnnotationTask, OcrBenchmarkRun, Report
from app.services.checks import field_accuracy
from app.services.extraction import extract_facts
from app.services.llm.factory import get_llm_provider
from app.services.metrics import mean_metric, proportion_metric
from app.services.ocr.metrics import ocr_error_metrics
from app.services.ocr.pipeline import run_ocr_on_report
from app.services.scan_assets import is_real_scan_manifest, load_manifest

logger = logging.getLogger(__name__)


def _manifest_for(report: Report) -> dict[str, Any]:
    return report.scan_manifest or load_manifest(report.tcga_barcode) or {}


async def run_ocr_benchmark(
    db: Session,
    *,
    engine_name: str | None = None,
    report_ids: list[int] | None = None,
    force: bool = False,
    require_real_scans: bool = True,
) -> OcrBenchmarkRun:
    """Stratified OCR CER/WER on real scans only (+ optional extraction impact)."""
    q = db.query(Report)
    if report_ids:
        q = q.filter(Report.id.in_(report_ids))
    reports = q.order_by(Report.cancer_type, Report.id).all()
    if not reports:
        raise ValueError("No reports to benchmark")

    gold_by_report: dict[int, dict] = {}
    for task in (
        db.query(AnnotationTask)
        .filter(AnnotationTask.status == "completed", AnnotationTask.gold_labels.isnot(None))
        .all()
    ):
        gold_by_report[task.report_id] = task.gold_labels  # type: ignore[assignment]

    provider = get_llm_provider()
    per_report: list[dict[str, Any]] = []
    by_cancer_cers: dict[str, list[float]] = defaultdict(list)
    by_cancer_wers: dict[str, list[float]] = defaultdict(list)

    extract_from_our: list[bool] = []
    extract_from_ref: list[bool] = []

    engine_tag = engine_name or "tesseract"
    engine_version = ""
    n_real = 0
    n_facsimile_excluded = 0
    n_missing = 0

    for report in reports:
        manifest = _manifest_for(report)
        source = manifest.get("source")
        if require_real_scans and not is_real_scan_manifest(manifest):
            if source == "ocr_text_facsimile":
                n_facsimile_excluded += 1
                per_report.append(
                    {
                        "report_id": report.id,
                        "tcga_barcode": report.tcga_barcode,
                        "cancer_type": report.cancer_type,
                        "scan_source": source,
                        "scored": False,
                        "excluded_reason": "facsimile_circular_vs_textract_reference",
                    }
                )
            else:
                n_missing += 1
                per_report.append(
                    {
                        "report_id": report.id,
                        "tcga_barcode": report.tcga_barcode,
                        "cancer_type": report.cancer_type,
                        "scan_source": source,
                        "scored": False,
                        "excluded_reason": "no_real_scan_cached",
                    }
                )
            continue

        try:
            ocr_run = await run_ocr_on_report(
                db, report, engine_name=engine_name or "tesseract", force=force, allow_live=True
            )
        except FileNotFoundError as exc:
            n_missing += 1
            per_report.append(
                {
                    "report_id": report.id,
                    "tcga_barcode": report.tcga_barcode,
                    "cancer_type": report.cancer_type,
                    "scan_source": source,
                    "scored": False,
                    "error": str(exc),
                }
            )
            continue

        n_real += 1
        engine_tag = ocr_run.engine
        engine_version = ocr_run.engine_version
        # Reuse CER/WER persisted on the OCR run (avoid recompute on the loop).
        if ocr_run.cer is not None and ocr_run.wer is not None:
            metrics = {
                "cer": float(ocr_run.cer),
                "wer": float(ocr_run.wer),
                **{
                    k: (ocr_run.meta_json or {}).get(k)
                    for k in ("ref_chars", "hyp_chars", "ref_words", "hyp_words")
                },
            }
        else:
            metrics = ocr_error_metrics(report.report_text, ocr_run.text)
        by_cancer_cers[report.cancer_type].append(metrics["cer"])
        by_cancer_wers[report.cancer_type].append(metrics["wer"])

        row: dict[str, Any] = {
            "report_id": report.id,
            "tcga_barcode": report.tcga_barcode,
            "cancer_type": report.cancer_type,
            "ocr_run_id": ocr_run.id,
            "engine": ocr_run.engine,
            "engine_version": ocr_run.engine_version,
            "duration_ms": ocr_run.duration_ms,
            "estimated_cost_usd": ocr_run.estimated_cost_usd,
            "scan_source": source,
            "scored": True,
            **metrics,
        }

        gold = gold_by_report.get(report.id)
        if gold:
            our_ext = await extract_facts(ocr_run.text, provider, prompt_name="extract_v1.txt")
            ref_ext = await extract_facts(
                report.report_text, provider, prompt_name="extract_v1.txt"
            )
            our_acc = field_accuracy(our_ext.facts.model_dump(), gold)
            ref_acc = field_accuracy(ref_ext.facts.model_dump(), gold)
            row["extraction"] = {
                "our_ocr": our_acc,
                "reference_textract": ref_acc,
            }
            for info in (our_acc.get("per_field") or {}).values():
                if info.get("scored"):
                    extract_from_our.append(bool(info.get("match")))
            for info in (ref_acc.get("per_field") or {}).values():
                if info.get("scored"):
                    extract_from_ref.append(bool(info.get("match")))

        per_report.append(row)
        logger.info(
            "ocr.benchmark barcode=%s source=%s cer=%.3f wer=%.3f ms=%.0f",
            report.tcga_barcode,
            source,
            metrics["cer"],
            metrics["wer"],
            ocr_run.duration_ms or 0,
        )

    if n_real == 0:
        raise ValueError(
            "No real scan pages available to score. Facsimiles are excluded "
            "(circular vs Textract). Fetch Tatonetti/GDC pages first."
        )

    all_cers = [r["cer"] for r in per_report if r.get("scored") and "cer" in r]
    all_wers = [r["wer"] for r in per_report if r.get("scored") and "wer" in r]
    summary: dict[str, Any] = {
        "n_reports_considered": len(reports),
        "n_real_scans_scored": n_real,
        "n_facsimile_excluded": n_facsimile_excluded,
        "n_missing_scan": n_missing,
        "engine": engine_tag,
        "engine_version": engine_version,
        "scan_sources_allowed": ["tatonetti_textract_input", "gdc_pdf"],
        "integrity_note": (
            "CER/WER are computed only on authentic page images (Tatonetti Textract "
            "inputs or GDC PDF renders). OCR-text facsimiles are excluded because they "
            "are rendered from the Textract reference and would circularly understate error."
        ),
        "overall": {
            "cer": mean_metric("cer", all_cers) if all_cers else None,
            "wer": mean_metric("wer", all_wers) if all_wers else None,
        },
        "by_cancer_type": {},
        "extraction_impact": {},
    }
    for ct in sorted(set(by_cancer_cers) | set(by_cancer_wers)):
        summary["by_cancer_type"][ct] = {
            "cer": mean_metric("cer", by_cancer_cers[ct]) if by_cancer_cers[ct] else None,
            "wer": mean_metric("wer", by_cancer_wers[ct]) if by_cancer_wers[ct] else None,
            "n": len(by_cancer_cers.get(ct) or by_cancer_wers.get(ct) or []),
        }

    if extract_from_our or extract_from_ref:
        summary["extraction_impact"] = {
            "field_accuracy_from_our_ocr": (
                proportion_metric(
                    "field_accuracy_from_our_ocr",
                    sum(1 for x in extract_from_our if x),
                    len(extract_from_our),
                )
                if extract_from_our
                else None
            ),
            "field_accuracy_from_reference": (
                proportion_metric(
                    "field_accuracy_from_reference",
                    sum(1 for x in extract_from_ref if x),
                    len(extract_from_ref),
                )
                if extract_from_ref
                else None
            ),
            "n_gold_fields_our": len(extract_from_our),
            "n_gold_fields_ref": len(extract_from_ref),
            "note": (
                "Compares extract→field accuracy when the input text is our OCR of a "
                "real scan vs TCGA-Reports (Textract) reference, scored against gold."
            ),
        }

    run = OcrBenchmarkRun(
        engine=engine_tag or "unknown",
        engine_version=engine_version or "",
        report_ids=[r.id for r in reports],
        results_json={"per_report": per_report, "summary": summary},
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run
