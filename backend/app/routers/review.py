"""Clinician review routes.

Clinicians see report + explanation but NOT model name or prompt version
(to reduce bias in scoring).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.deps import ClinicianUser, DbDep
from app.models import Generation, Report, ReviewTask, TaskStatus, utcnow
from app.schemas import ReviewSubmit, ReviewTaskOut
from app.services.grounding import annotate_explanation_grounding

router = APIRouter(prefix="/api/review", tags=["review"])


@router.get("/tasks", response_model=list[ReviewTaskOut])
def list_tasks(db: DbDep, user: ClinicianUser) -> list[ReviewTaskOut]:
    q = db.query(ReviewTask)
    if user.role != "admin":
        q = q.filter(ReviewTask.assignee_id == user.id)
    return [ReviewTaskOut.model_validate(t) for t in q.order_by(ReviewTask.id).all()]


@router.get("/tasks/{task_id}", response_model=ReviewTaskOut)
def get_task(task_id: int, db: DbDep, user: ClinicianUser) -> ReviewTaskOut:
    task = db.query(ReviewTask).filter(ReviewTask.id == task_id).first()
    if not task:
        raise HTTPException(404, "Task not found")
    if user.role != "admin" and task.assignee_id != user.id:
        raise HTTPException(403, "Not your task")

    gen = db.query(Generation).filter(Generation.id == task.generation_id).first()
    if not gen:
        raise HTTPException(404, "Generation not found")
    report = db.query(Report).filter(Report.id == gen.report_id).first()

    out = ReviewTaskOut.model_validate(task)
    # Intentionally omit provider/model/prompt versions
    if report:
        out.report_text = report.report_text
        out.cancer_type = report.cancer_type
        out.tcga_barcode = report.tcga_barcode
    out.facts = gen.facts_json
    # Ensure clinician UI sees grounding flags even for older cached generations.
    explanation = gen.explanation_json or {"sentences": []}
    if report and report.report_text:
        explanation = annotate_explanation_grounding(explanation, report.report_text)
    out.explanation = explanation
    return out


@router.post("/tasks/{task_id}", response_model=ReviewTaskOut)
def submit_review(task_id: int, body: ReviewSubmit, db: DbDep, user: ClinicianUser) -> ReviewTaskOut:
    task = db.query(ReviewTask).filter(ReviewTask.id == task_id).first()
    if not task:
        raise HTTPException(404, "Task not found")
    if user.role != "admin" and task.assignee_id != user.id:
        raise HTTPException(403, "Not your task")
    task.scores = body.scores.model_dump()
    task.flagged_sentences = body.flagged_sentences
    task.comments = body.comments
    task.status = TaskStatus.completed.value
    task.completed_at = utcnow()
    db.commit()
    db.refresh(task)
    return ReviewTaskOut.model_validate(task)
