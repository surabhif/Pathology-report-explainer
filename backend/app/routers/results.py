"""Results dashboard: metrics with 95% CIs + CSV export."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

from app.deps import AdminUser, CurrentUser, DbDep
from app.models import AnnotationTask, AutoCheckRun, Generation, OcrBenchmarkRun, ReviewTask
from app.schemas import (
    ClinicianScoreSummary,
    FailureExample,
    InterRaterSummary,
    MetricWithCI,
    ResultsSummary,
)
from app.services.checks import FACT_FIELDS
from app.services.metrics import (
    inter_rater_agreement,
    mean_metric,
    proportion_metric,
    results_to_csv,
    summarize_check_results,
)

router = APIRouter(prefix="/api/results", tags=["results"])


def _collect_check_runs(db) -> tuple[list[dict], dict[str, list[dict]], list[dict]]:
    """Flatten AutoCheckRun.results_json into per-generation check dicts, overall + by cancer.

    Also returns the raw per-generation items (with ids) for failure examples.
    """
    all_checks: list[dict] = []
    by_cancer: dict[str, list[dict]] = {}
    items: list[dict] = []
    for run in db.query(AutoCheckRun).order_by(AutoCheckRun.id).all():
        for item in (run.results_json or {}).get("per_generation", []):
            checks = item.get("checks") or {}
            all_checks.append(checks)
            ct = item.get("cancer_type") or "UNKNOWN"
            by_cancer.setdefault(ct, []).append(checks)
            items.append(item)
    return all_checks, by_cancer, items


def _per_field_metrics(all_checks: list[dict]) -> dict[str, list[MetricWithCI]]:
    """Build Wilson metrics for each fact field from field_accuracy.per_field."""
    tallies: dict[str, list[bool]] = {f: [] for f in FACT_FIELDS}
    for checks in all_checks:
        fa = checks.get("field_accuracy") or {}
        per = fa.get("per_field") or {}
        for field, info in per.items():
            if info.get("scored"):
                tallies.setdefault(field, []).append(bool(info.get("match")))
    out: dict[str, list[MetricWithCI]] = {}
    for field, matches in tallies.items():
        if not matches:
            continue
        m = proportion_metric(field, sum(1 for x in matches if x), len(matches))
        out[field] = [MetricWithCI(**m)]
    return out


def _clinician_scores(db) -> ClinicianScoreSummary:
    reviews = (
        db.query(ReviewTask)
        .filter(ReviewTask.status == "completed", ReviewTask.scores.isnot(None))
        .all()
    )
    buckets: dict[str, list[float]] = {
        "accuracy": [],
        "completeness": [],
        "harm_potential": [],
    }
    for r in reviews:
        scores = r.scores or {}
        for key in buckets:
            if scores.get(key) is not None:
                buckets[key].append(float(scores[key]))

    def as_metric(name: str, values: list[float]) -> MetricWithCI | None:
        if not values:
            return None
        return MetricWithCI(**mean_metric(name, values))

    return ClinicianScoreSummary(
        accuracy=as_metric("accuracy", buckets["accuracy"]),
        completeness=as_metric("completeness", buckets["completeness"]),
        harm_potential=as_metric("harm_potential", buckets["harm_potential"]),
        n_reviews=len(reviews),
    )


def _inter_rater(db) -> InterRaterSummary:
    """Compute pairwise exact agreement across clinicians on the same generation."""
    reviews = (
        db.query(ReviewTask)
        .filter(ReviewTask.status == "completed", ReviewTask.scores.isnot(None))
        .all()
    )
    by_gen: dict[int, list[dict]] = {}
    for r in reviews:
        by_gen.setdefault(r.generation_id, []).append(r.scores or {})
    raw = inter_rater_agreement(by_gen)
    metric = None
    if raw.get("metric"):
        metric = MetricWithCI(**raw["metric"])
    return InterRaterSummary(
        available=bool(raw.get("available")),
        n_items_with_multiple_raters=int(raw.get("n_items_with_multiple_raters") or 0),
        n_pairs=int(raw.get("n_pairs") or 0),
        metric=metric,
    )


def _failure_examples(items: list[dict], limit: int = 12) -> list[FailureExample]:
    examples: list[FailureExample] = []
    for item in items:
        checks = item.get("checks") or {}
        gid = int(item.get("generation_id") or 0)
        rid = int(item.get("report_id") or 0)
        ct = item.get("cancer_type")

        ng = checks.get("number_grounding") or {}
        if ng and ng.get("pass") is False:
            examples.append(
                FailureExample(
                    generation_id=gid,
                    report_id=rid,
                    cancer_type=ct,
                    check_name="number_grounding",
                    detail=f"unsupported numbers: {ng.get('unsupported')}",
                )
            )

        us = checks.get("unsupported_sentences") or {}
        flagged = us.get("flagged") or us.get("unsupported") or []
        if flagged or us.get("unsupported_count"):
            examples.append(
                FailureExample(
                    generation_id=gid,
                    report_id=rid,
                    cancer_type=ct,
                    check_name="unsupported_sentences",
                    detail=f"count={us.get('unsupported_count')} flagged={flagged}",
                )
            )

        rl = checks.get("reading_level") or {}
        if rl and rl.get("meets_target") is False:
            examples.append(
                FailureExample(
                    generation_id=gid,
                    report_id=rid,
                    cancer_type=ct,
                    check_name="reading_level",
                    detail=f"explanation_grade={rl.get('explanation_grade')}",
                )
            )

        fa = checks.get("field_accuracy") or {}
        per = fa.get("per_field") or {}
        for field, info in per.items():
            if info.get("scored") and info.get("match") is False:
                examples.append(
                    FailureExample(
                        generation_id=gid,
                        report_id=rid,
                        cancer_type=ct,
                        check_name=f"field_accuracy:{field}",
                        detail=f"gold={info.get('gold')} predicted={info.get('predicted')}",
                    )
                )

        if len(examples) >= limit:
            break
    return examples[:limit]


@router.get("/summary", response_model=ResultsSummary)
def summary(db: DbDep, _user: CurrentUser) -> ResultsSummary:
    """Any authenticated user can view aggregate metrics (no PHI in summary)."""
    all_checks, by_cancer, items = _collect_check_runs(db)
    metrics = [MetricWithCI(**m) for m in summarize_check_results(all_checks)]
    by_ct = {
        ct: [MetricWithCI(**m) for m in summarize_check_results(rows)]
        for ct, rows in by_cancer.items()
    }
    return ResultsSummary(
        metrics=metrics,
        by_cancer_type=by_ct,
        by_field=_per_field_metrics(all_checks),
        auto_check_runs=db.query(AutoCheckRun).count(),
        generations=db.query(Generation).filter(Generation.is_fallback.is_(False)).count(),
        gold_annotations=db.query(AnnotationTask).filter(AnnotationTask.status == "completed").count(),
        clinician_reviews=db.query(ReviewTask).filter(ReviewTask.status == "completed").count(),
        clinician_scores=_clinician_scores(db),
        inter_rater=_inter_rater(db),
        failure_examples=_failure_examples(items),
        fallback_generations=db.query(Generation).filter(Generation.is_fallback.is_(True)).count(),
        fallback_excluded_from_metrics=True,
        ocr_benchmark=_latest_ocr_benchmark(db),
    )


def _latest_ocr_benchmark(db) -> dict | None:
    row = db.query(OcrBenchmarkRun).order_by(OcrBenchmarkRun.id.desc()).first()
    if not row:
        return None
    payload = row.results_json or {}
    return {
        "id": row.id,
        "engine": row.engine,
        "engine_version": row.engine_version,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "summary": payload.get("summary") or {},
        "n_reports": len(row.report_ids or []),
        "reference": "TCGA-Reports (Kefeli et al.; AWS Textract)",
    }


@router.get("/export.csv")
def export_csv(db: DbDep, _admin: AdminUser) -> PlainTextResponse:
    all_checks, by_cancer, _items = _collect_check_runs(db)
    rows = []
    for m in summarize_check_results(all_checks):
        rows.append({"scope": "overall", "cancer_type": "", **m})
    for ct, checks in by_cancer.items():
        for m in summarize_check_results(checks):
            rows.append({"scope": "cancer_type", "cancer_type": ct, **m})
    # Also include per-generation detail (ids only — no report text)
    for run in db.query(AutoCheckRun).all():
        for item in (run.results_json or {}).get("per_generation", []):
            checks = item.get("checks") or {}
            ng = checks.get("number_grounding") or {}
            us = checks.get("unsupported_sentences") or {}
            rl = checks.get("reading_level") or {}
            fa = checks.get("field_accuracy") or {}
            rows.append(
                {
                    "scope": "generation",
                    "cancer_type": item.get("cancer_type"),
                    "generation_id": item.get("generation_id"),
                    "report_id": item.get("report_id"),
                    "field_accuracy": fa.get("accuracy"),
                    "number_grounding_pass": ng.get("pass"),
                    "support_rate": us.get("support_rate"),
                    "explanation_grade": rl.get("explanation_grade"),
                }
            )
    csv_text = results_to_csv(rows)
    return PlainTextResponse(csv_text, media_type="text/csv")
