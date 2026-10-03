"""SQLAlchemy ORM models for the Pathology Report Explainer MVP.

Roles: admin | annotator | clinician
PHI policy: never log full report text or user PHI beyond evaluation needs.
"""

from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class UserRole(str, enum.Enum):
    admin = "admin"
    annotator = "annotator"
    clinician = "clinician"


class PromptKind(str, enum.Enum):
    extract = "extract"
    explain = "explain"


class BatchType(str, enum.Enum):
    annotate = "annotate"
    review = "review"
    auto_check = "auto_check"


class TaskStatus(str, enum.Enum):
    pending = "pending"
    in_progress = "in_progress"
    completed = "completed"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)  # UserRole value
    invite_token: Mapped[str | None] = mapped_column(String(128), unique=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    sessions: Mapped[list[SessionToken]] = relationship(back_populates="user")


class SessionToken(Base):
    __tablename__ = "session_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    token: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user: Mapped[User] = relationship(back_populates="sessions")


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tcga_barcode: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    cancer_type: Mapped[str] = mapped_column(String(16), nullable=False, index=True)  # BRCA, COAD, LUAD
    project_id: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    report_text: Mapped[str] = mapped_column(Text, nullable=False)
    gdc_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Cached scan journey assets (GDC PDF page renders or labeled OCR facsimiles).
    scan_manifest: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="tcga")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PromptVersion(Base):
    __tablename__ = "prompt_versions"
    __table_args__ = (UniqueConstraint("name", "version", "kind", name="uq_prompt_name_ver_kind"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)  # extract | explain
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)


class Generation(Base):
    """Cached model output for a report + prompt/model combo.

    PHI note: facts_json / explanation_json may contain quotes from reports;
    do not write them to application logs.
    """

    __tablename__ = "generations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("reports.id"), nullable=False, index=True)
    prompt_extract_version: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_explain_version: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    # Honest fallback labeling: when validation fails we store mock output and
    # set is_fallback=True — never attribute heuristic output to xAI/OpenAI.
    is_fallback: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    fallback_reason: Mapped[str | None] = mapped_column(String(128), nullable=True)
    requested_provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    requested_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # True when we re-prompted after detecting unsupported explanation sentences.
    explanation_retried: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Snapshot of unsupported_sentences check (flagged indices/reasons) at save time.
    grounding_check_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Which text was explained: reference (TCGA-Reports) | our_ocr
    text_source: Mapped[str] = mapped_column(String(32), nullable=False, default="reference")
    ocr_run_id: Mapped[int | None] = mapped_column(ForeignKey("ocr_runs.id"), nullable=True)
    facts_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    explanation_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    reading_level_original: Mapped[float | None] = mapped_column(Float, nullable=True)
    reading_level_explanation: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class OcrRun(Base):
    """Cached OCR transcript for a report + engine/version (PathExplain-owned OCR)."""

    __tablename__ = "ocr_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("reports.id"), nullable=False, index=True)
    engine: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    engine_version: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    pages_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    duration_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    estimated_cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    cer: Mapped[float | None] = mapped_column(Float, nullable=True)
    wer: Mapped[float | None] = mapped_column(Float, nullable=True)
    cache_key: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    meta_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class OcrBenchmarkRun(Base):
    """Aggregated OCR vs Textract reference + extraction-impact study."""

    __tablename__ = "ocr_benchmark_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    engine: Mapped[str] = mapped_column(String(64), nullable=False)
    engine_version: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    report_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    results_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class EvaluationSet(Base):
    __tablename__ = "evaluation_sets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    cancer_types: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    report_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TaskBatch(Base):
    __tablename__ = "task_batches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    batch_type: Mapped[str] = mapped_column(String(32), nullable=False)  # annotate|review|auto_check
    evaluation_set_id: Mapped[int | None] = mapped_column(ForeignKey("evaluation_sets.id"), nullable=True)
    assigned_user_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AnnotationTask(Base):
    """Gold labeling task. Annotators must NOT see model generations."""

    __tablename__ = "annotation_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("task_batches.id"), nullable=False, index=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("reports.id"), nullable=False)
    assignee_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default=TaskStatus.pending.value)
    # field -> {value, quote, start, end}  (gold spans)
    gold_labels: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ReviewTask(Base):
    """Clinician review of a generation. Hide model/prompt version from clinician UI."""

    __tablename__ = "review_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("task_batches.id"), nullable=False, index=True)
    generation_id: Mapped[int] = mapped_column(ForeignKey("generations.id"), nullable=False)
    assignee_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default=TaskStatus.pending.value)
    # {accuracy, completeness, harm_potential} each 1-5
    scores: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    flagged_sentences: Mapped[list | None] = mapped_column(JSON, nullable=True)
    comments: Mapped[str | None] = mapped_column(Text, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AutoCheckRun(Base):
    __tablename__ = "auto_check_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    batch_id: Mapped[int | None] = mapped_column(ForeignKey("task_batches.id"), nullable=True)
    generation_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    results_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    prompt_tags: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    model_tags: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Rubric(Base):
    __tablename__ = "rubrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    content: Mapped[dict] = mapped_column(JSON, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
