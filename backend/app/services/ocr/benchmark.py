"""OCR benchmark vs TCGA-Reports (Textract) reference + extraction impact."""

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

logger = logging.getLogger(__name__)


async def run_ocr_benchmark(
    db: Session,
    *,
    engine_name: str | None = None,
    report_ids: list[int] | None = None,
    force: bool = False,
) -> OcrBenchmarkRun:
    """Stratified sample (all seeded reports if ids omitted): CER/WER + extraction accuracy."""
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

    # Extraction tallies: our_ocr vs reference vs gold
    extract_from_our: list[bool] = []
    extract_from_ref: list[bool] = []

    engine_tag = engine_name
    engine_version = ""

    for report in reports:
        try:
            ocr_run = await run_ocr_on_report(
                db, report, engine_name=engine_name, force=force
            )
        except FileNotFoundError as exc:
            per_report.append(
                {
                    "report_id": report.id,
                    "tcga_barcode": report.tcga_barcode,
                    "cancer_type": report.cancer_type,
                    "error": str(exc),
                }
            )
            continue

        engine_tag = ocr_run.engine
        engine_version = ocr_run.engine_version
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
            **metrics,
        }

        gold = gold_by_report.get(report.id)
        if gold:
            # Extract from our OCR text
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
            # Micro-average field matches for summary
            for info in (our_acc.get("per_field") or {}).values():
                if info.get("scored"):
                    extract_from_our.append(bool(info.get("match")))
            for info in (ref_acc.get("per_field") or {}).values():
                if info.get("scored"):
                    extract_from_ref.append(bool(info.get("match")))

        per_report.append(row)
        logger.info(
            "ocr.benchmark barcode=%s cer=%.3f wer=%.3f ms=%.0f",
            report.tcga_barcode,
            metrics["cer"],
            metrics["wer"],
            ocr_run.duration_ms or 0,
        )

    all_cers = [r["cer"] for r in per_report if "cer" in r]
    all_wers = [r["wer"] for r in per_report if "wer" in r]
    summary: dict[str, Any] = {
        "n_reports": len([r for r in per_report if "cer" in r]),
        "engine": engine_tag,
        "engine_version": engine_version,
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
                "Compares extract→field accuracy when the input text is our OCR vs "
                "TCGA-Reports (Textract) reference, scored against gold labels when present."
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
