"""Admin routes: invites, import, evaluation sets, batches, progress, auto-checks."""

from __future__ import annotations

import logging

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.auth import create_invite_user
from app.deps import AdminUser, DbDep
from app.models import (
    AnnotationTask,
    AutoCheckRun,
    EvaluationSet,
    Generation,
    Report,
    ReviewTask,
    TaskBatch,
    TaskStatus,
    User,
    utcnow,
)
from app.routers.public import run_explain_pipeline
from app.schemas import (
    AutoCheckRequest,
    EvaluationSetCreate,
    EvaluationSetOut,
    ImportReportsRequest,
    InviteCreate,
    ProgressOut,
    TaskBatchCreate,
    TaskBatchOut,
    UserOut,
)
from app.services.checks import run_all_checks
from app.services.import_reports import import_report

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.post("/invites", response_model=UserOut)
def create_invite(body: InviteCreate, db: DbDep, _admin: AdminUser) -> UserOut:
    user = create_invite_user(
        db,
        email=body.email,
        name=body.name,
        role=body.role,
        invite_token=body.invite_token,
    )
    return UserOut.model_validate(user)


@router.get("/users", response_model=list[UserOut])
def list_users(db: DbDep, _admin: AdminUser) -> list[UserOut]:
    return [UserOut.model_validate(u) for u in db.query(User).order_by(User.id).all()]


@router.post("/import")
def import_reports(body: ImportReportsRequest, db: DbDep, _admin: AdminUser) -> dict:
    created = []
    for item in body.reports:
        r = import_report(
            db,
            tcga_barcode=item.tcga_barcode,
            cancer_type=item.cancer_type,
            report_text=item.report_text,
            project_id=item.project_id or None,
            gdc_metadata=item.gdc_metadata,
            source=item.source,
        )
        created.append({"id": r.id, "tcga_barcode": r.tcga_barcode})
    return {"imported": len(created), "reports": created}


@router.post("/evaluation-sets", response_model=EvaluationSetOut)
def create_eval_set(body: EvaluationSetCreate, db: DbDep, _admin: AdminUser) -> EvaluationSetOut:
    row = EvaluationSet(
        name=body.name,
        cancer_types=body.cancer_types,
        report_ids=body.report_ids,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return EvaluationSetOut.model_validate(row)


@router.get("/evaluation-sets", response_model=list[EvaluationSetOut])
def list_eval_sets(db: DbDep, _admin: AdminUser) -> list[EvaluationSetOut]:
    return [EvaluationSetOut.model_validate(r) for r in db.query(EvaluationSet).all()]


@router.post("/batches", response_model=TaskBatchOut)
async def create_batch(body: TaskBatchCreate, db: DbDep, _admin: AdminUser) -> TaskBatchOut:
    """Create a task batch and materialize AnnotationTask / ReviewTask rows."""
    batch = TaskBatch(
        name=body.name,
        batch_type=body.batch_type,
        evaluation_set_id=body.evaluation_set_id,
        assigned_user_ids=body.assigned_user_ids,
        status="active",
    )
    db.add(batch)
    db.commit()
    db.refresh(batch)

    report_ids: list[int] = []
    if body.evaluation_set_id:
        eset = db.query(EvaluationSet).filter(EvaluationSet.id == body.evaluation_set_id).first()
        if not eset:
            raise HTTPException(404, "Evaluation set not found")
        report_ids = list(eset.report_ids or [])

    assignees = body.assigned_user_ids or []
    if not assignees:
        raise HTTPException(400, "assigned_user_ids required")

    if body.batch_type == "annotate":
        for i, rid in enumerate(report_ids):
            assignee = assignees[i % len(assignees)]
            db.add(
                AnnotationTask(
                    batch_id=batch.id,
                    report_id=rid,
                    assignee_id=assignee,
                    status=TaskStatus.pending.value,
                )
            )
    elif body.batch_type == "review":
        # Ensure generations exist (mock pipeline) then assign review tasks
        for i, rid in enumerate(report_ids):
            report = db.query(Report).filter(Report.id == rid).first()
            if not report:
                continue
            gen = await run_explain_pipeline(db, report)
            assignee = assignees[i % len(assignees)]
            db.add(
                ReviewTask(
                    batch_id=batch.id,
                    generation_id=gen.id,
                    assignee_id=assignee,
                    status=TaskStatus.pending.value,
                )
            )
    elif body.batch_type == "auto_check":
        pass  # runs created via /runs/auto-checks
    else:
        raise HTTPException(400, f"Unknown batch_type {body.batch_type}")

    db.commit()
    return TaskBatchOut.model_validate(batch)


@router.get("/batches", response_model=list[TaskBatchOut])
def list_batches(db: DbDep, _admin: AdminUser) -> list[TaskBatchOut]:
    return [TaskBatchOut.model_validate(b) for b in db.query(TaskBatch).order_by(TaskBatch.id).all()]


@router.get("/progress", response_model=ProgressOut)
def progress(db: DbDep, _admin: AdminUser) -> ProgressOut:
    return ProgressOut(
        annotation_pending=db.query(AnnotationTask).filter(AnnotationTask.status != "completed").count(),
        annotation_completed=db.query(AnnotationTask).filter(AnnotationTask.status == "completed").count(),
        review_pending=db.query(ReviewTask).filter(ReviewTask.status != "completed").count(),
        review_completed=db.query(ReviewTask).filter(ReviewTask.status == "completed").count(),
        total_reports=db.query(Report).count(),
        total_generations=db.query(Generation).count(),
    )


@router.post("/runs/auto-checks")
def run_auto_checks(body: AutoCheckRequest, db: DbDep, _admin: AdminUser) -> dict:
    """Run automatic evaluation checks over generations (optionally scoped)."""
    q = db.query(Generation)
    if body.generation_ids:
        q = q.filter(Generation.id.in_(body.generation_ids))
    elif body.evaluation_set_id:
        eset = db.query(EvaluationSet).filter(EvaluationSet.id == body.evaluation_set_id).first()
        if not eset:
            raise HTTPException(404, "Evaluation set not found")
        q = q.filter(Generation.report_id.in_(list(eset.report_ids or [])))
    generations = q.all()
    if not generations:
        raise HTTPException(400, "No generations to check")

    # Gold labels by report_id (latest completed annotation)
    gold_by_report: dict[int, dict] = {}
    for task in (
        db.query(AnnotationTask)
        .filter(AnnotationTask.status == "completed", AnnotationTask.gold_labels.isnot(None))
        .all()
    ):
        gold_by_report[task.report_id] = task.gold_labels  # type: ignore[assignment]

    per_gen = []
    fallback_gen = []
    prompt_tags: set[str] = set()
    model_tags: set[str] = set()
    for gen in generations:
        report = db.query(Report).filter(Report.id == gen.report_id).first()
        if not report:
            continue
        entry = {
            "generation_id": gen.id,
            "report_id": report.id,
            "cancer_type": report.cancer_type,
            "provider": gen.provider,
            "model": gen.model,
            "is_fallback": bool(gen.is_fallback),
            "fallback_reason": gen.fallback_reason,
            "requested_provider": gen.requested_provider,
            "requested_model": gen.requested_model,
        }
        # Evaluation integrity: fallback (heuristic) generations are tracked
        # separately and excluded from primary automatic-check metrics.
        if gen.is_fallback:
            fallback_gen.append(entry)
            continue
        checks = run_all_checks(
            facts=gen.facts_json,
            explanation=gen.explanation_json,
            report_text=report.report_text,
            gold_labels=gold_by_report.get(report.id),
            gdc_metadata=report.gdc_metadata,
            cancer_type=report.cancer_type,
        )
        entry["checks"] = checks
        per_gen.append(entry)
        prompt_tags.add(f"{gen.prompt_extract_version}+{gen.prompt_explain_version}")
        model_tags.add(f"{gen.provider}:{gen.model}")

    run = AutoCheckRun(
        batch_id=body.batch_id,
        generation_ids=[g.id for g in generations],
        results_json={
            "per_generation": per_gen,
            "count": len(per_gen),
            "fallback_generations": fallback_gen,
            "fallback_count": len(fallback_gen),
            "excluded_fallbacks_from_metrics": True,
        },
        prompt_tags=",".join(sorted(prompt_tags)),
        model_tags=",".join(sorted(model_tags)),
        created_at=utcnow(),
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    logger.info(
        "auto_checks.completed run_id=%s n=%d fallbacks_excluded=%d",
        run.id,
        len(per_gen),
        len(fallback_gen),
    )
    return {
        "run_id": run.id,
        "count": len(per_gen),
        "fallback_count": len(fallback_gen),
        "results": run.results_json,
    }


@router.post("/ocr/benchmark")
async def ocr_benchmark(
    db: DbDep,
    _admin: AdminUser,
    engine: str | None = None,
    force: bool = False,
) -> dict:
    """Run stratified OCR benchmark vs TCGA-Reports (Textract) + extraction impact."""
    from app.services.ocr.benchmark import run_ocr_benchmark

    try:
        run = await run_ocr_benchmark(db, engine_name=engine, force=force)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    summary = (run.results_json or {}).get("summary") or {}
    return {
        "benchmark_id": run.id,
        "engine": run.engine,
        "engine_version": run.engine_version,
        "summary": summary,
        "n_reports": len(run.report_ids or []),
    }


@router.post("/ocr/upload-test")
async def ocr_upload_test(
    db: DbDep,
    _admin: AdminUser,
    file: UploadFile = File(...),
    engine: str | None = None,
    acknowledge_deidentified: bool = Form(False),
) -> dict:
    """Admin-only OCR of a de-identified / TCGA test page image.

    Public demo never accepts uploads (PHI risk). This endpoint requires an
    explicit acknowledgement and stores only OCR text + metrics needed for eval.
    """
    if not acknowledge_deidentified:
        raise HTTPException(
            400,
            "Set acknowledge_deidentified=true. Only TCGA or de-identified test files — never real PHI.",
        )
    from app.services.ocr.factory import get_ocr_engine

    name = (file.filename or "").lower()
    if not any(name.endswith(ext) for ext in (".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp")):
        raise HTTPException(400, "Only page images are accepted (.jpg/.png/.tif)")
    blob = await file.read()
    if len(blob) > 8_000_000:
        raise HTTPException(400, "File too large (max 8MB)")
    if not blob:
        raise HTTPException(400, "Empty file")

    eng = get_ocr_engine(engine)
    mime = "image/png" if name.endswith(".png") else "image/jpeg"
    page = await eng.ocr_image_bytes(blob, mime=mime, page=1)
    # Do not persist the uploaded image bytes — evaluation text only, ephemeral response.
    return {
        "warning": (
            "Admin test OCR only. Do not upload real patient reports. "
            "Image bytes are not stored; only the returned transcript is echoed."
        ),
        "engine": eng.engine_id(),
        "engine_version": eng.engine_version(),
        "duration_ms": page.duration_ms,
        "text": page.text,
        "chars": len(page.text),
        "filename": file.filename,
    }
