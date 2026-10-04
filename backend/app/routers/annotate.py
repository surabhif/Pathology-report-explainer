"""Annotator routes: gold labeling. NEVER return model generations."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.deps import AnnotatorUser, DbDep
from app.models import AnnotationTask, Report, TaskStatus, utcnow
from app.schemas import AnnotationTaskOut, GoldLabelSubmit, ReportDetail

router = APIRouter(prefix="/api/annotate", tags=["annotate"])


@router.get("/tasks", response_model=list[AnnotationTaskOut])
def list_tasks(db: DbDep, user: AnnotatorUser) -> list[AnnotationTaskOut]:
    q = db.query(AnnotationTask)
    if user.role != "admin":
        q = q.filter(AnnotationTask.assignee_id == user.id)
    tasks = q.order_by(AnnotationTask.id).all()
    return [AnnotationTaskOut.model_validate(t) for t in tasks]


@router.get("/tasks/{task_id}", response_model=AnnotationTaskOut)
def get_task(task_id: int, db: DbDep, user: AnnotatorUser) -> AnnotationTaskOut:
    task = db.query(AnnotationTask).filter(AnnotationTask.id == task_id).first()
    if not task:
        raise HTTPException(404, "Task not found")
    if user.role != "admin" and task.assignee_id != user.id:
        raise HTTPException(403, "Not your task")
    report = db.query(Report).filter(Report.id == task.report_id).first()
    out = AnnotationTaskOut.model_validate(task)
    if report:
        # Explicitly return report text only — no generation fields.
        out.report = ReportDetail.model_validate(report)
    return out


@router.post("/tasks/{task_id}", response_model=AnnotationTaskOut)
def submit_gold(task_id: int, body: GoldLabelSubmit, db: DbDep, user: AnnotatorUser) -> AnnotationTaskOut:
    task = db.query(AnnotationTask).filter(AnnotationTask.id == task_id).first()
    if not task:
        raise HTTPException(404, "Task not found")
    if user.role != "admin" and task.assignee_id != user.id:
        raise HTTPException(403, "Not your task")
    task.gold_labels = {
        k: (v.model_dump() if v is not None else None) for k, v in body.gold_labels.items()
    }
    task.status = TaskStatus.completed.value
    task.completed_at = utcnow()
    db.commit()
    db.refresh(task)
    return AnnotationTaskOut.model_validate(task)
