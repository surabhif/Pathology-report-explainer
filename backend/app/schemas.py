"""Pydantic request/response schemas.

Fact sheet: each field is FactSpan | null.
Explanation: list of grounded sentences with source_fact_keys + quote.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, EmailStr, Field


Role = Literal["admin", "annotator", "clinician"]
CancerType = Literal["BRCA", "COAD", "LUAD"]


# ---------------------------------------------------------------------------
# Facts / explanation structures
# ---------------------------------------------------------------------------


class FactSpan(BaseModel):
    """A single extracted fact grounded in a report quote with character offsets."""

    value: str | int | float | bool | dict[str, Any] | None = None
    quote: str | None = None
    start_char: int | None = None
    end_char: int | None = None


class FactSheet(BaseModel):
    """Structured pathology facts extracted from a report."""

    diagnosis_or_histologic_type: FactSpan | None = None
    grade: FactSpan | None = None
    tumor_size: FactSpan | None = None
    margins: FactSpan | None = None
    lymph_nodes_positive: FactSpan | None = None
    lymph_nodes_examined: FactSpan | None = None
    pathologic_tnm_stage: FactSpan | None = None
    biomarkers: FactSpan | None = None  # value is typically a dict e.g. {"ER": "positive", ...}


class ExplanationSentence(BaseModel):
    sentence: str
    source_fact_keys: list[str] = Field(default_factory=list)
    quote: str | None = None
    # Populated after generation — empty/not-in-report quotes are not "ok".
    grounding: dict[str, Any] | None = None


class ExplanationPayload(BaseModel):
    sentences: list[ExplanationSentence]


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


class RedeemInviteRequest(BaseModel):
    token: str


class UserOut(BaseModel):
    id: int
    email: EmailStr
    name: str
    role: Role

    model_config = {"from_attributes": True}


class SessionOut(BaseModel):
    session_token: str
    expires_at: datetime
    user: UserOut


class InviteCreate(BaseModel):
    email: EmailStr
    name: str
    role: Role
    invite_token: str | None = None  # optional; generated if omitted


# ---------------------------------------------------------------------------
# Reports / public
# ---------------------------------------------------------------------------


class ReportSummary(BaseModel):
    id: int
    tcga_barcode: str
    cancer_type: str
    project_id: str
    source: str

    model_config = {"from_attributes": True}


class ReportDetail(ReportSummary):
    report_text: str
    gdc_metadata: dict[str, Any] | None = None
    scan_manifest: dict[str, Any] | None = None


class ScanPageOut(BaseModel):
    page: int
    url: str
    width: int | None = None
    height: int | None = None


class OurOcrOut(BaseModel):
    """PathExplain-owned OCR transcript for stage 2 comparison."""

    ocr_run_id: int
    engine: str
    engine_version: str
    model: str | None = None
    text: str
    duration_ms: float | None = None
    estimated_cost_usd: float | None = None
    cer: float | None = None  # vs TCGA-Reports reference
    wer: float | None = None
    page_count: int = 0
    # precomputed = committed offline OCR; live = admin-triggered Tesseract/vision
    source: str = "precomputed"  # precomputed | live
    precomputed_at: str | None = None
    label: str = "Our OCR (PathExplain)"
    note: str = (
        "Transcribed by PathExplain from cached scan page images. "
        "Quotes in stage 3 are grounded in this text when text_source=our_ocr."
    )


class ReportJourneyOut(BaseModel):
    """Three-stage scan → OCR → explain journey metadata for the public demo."""

    report_id: int
    tcga_barcode: str
    cancer_type: str
    # Stage 1
    scan_source: str | None = None  # tatonetti_textract_input | gdc_pdf | None (facsimiles never exposed)
    scan_label: str | None = None
    scan_citation: str | None = None
    scan_pages: list[ScanPageOut] = Field(default_factory=list)
    # Stage 2 — reference OCR (TCGA-Reports / Textract) vs PathExplain OCR
    ocr_label: str = (
        "Machine-readable OCR text from TCGA-Reports (Kefeli et al., Patterns 2024; AWS Textract). "
        "Use as the reference transcript for CER/WER benchmarks."
    )
    ocr_citation: str = (
        "Kefeli et al., “TCGA-Reports: A Machine-Readable Pathology Report Resource for "
        "Benchmarking Text-Based AI Models”, Patterns 2024. Underlying scans: open-access TCGA / NCI GDC."
    )
    report_text: str  # reference (Textract) text
    our_ocr: OurOcrOut | None = None
    default_ocr_engine: str = "tesseract"
    available_ocr_engines: list[str] = Field(default_factory=lambda: ["tesseract", "xai_vision"])
    # Stage 1 is shown only when authentic scan pages are cached (never facsimiles).
    has_real_scan: bool = False
    scan_scorable: bool = False
    # text_source values that already have a cached Generation for the active provider
    # (opening a case can show stage 3 without a new LLM call when present).
    cached_text_sources: list[str] = Field(default_factory=list)
    # Stage 3 pointer — client loads explain separately
    explain_path: str


class OcrDiffOut(BaseModel):
    ops: list[dict[str, Any]] = Field(default_factory=list)
    changed: int = 0
    cer: float | None = None
    wer: float | None = None


class ExplainResponse(BaseModel):
    report_id: int
    generation_id: int
    # Report text needed so the public UI can highlight grounding quotes.
    report_text: str = ""
    facts: FactSheet
    explanation: ExplanationPayload
    reading_level_original: float | None = None
    reading_level_explanation: float | None = None
    # Public endpoint may omit provider/model details for clinicians;
    # included for demo transparency on public explain.
    provider: str | None = None
    model: str | None = None
    # Honest fallback labeling (heuristic used after hosted-model validation failure).
    is_fallback: bool = False
    fallback_reason: str | None = None
    requested_provider: str | None = None
    requested_model: str | None = None
    # True when the explainer re-asked the model after unsupported sentences.
    explanation_retried: bool = False
    # Snapshot of unsupported_sentences (+ reading_level) check at generation time.
    grounding_check: dict[str, Any] | None = None
    # True when a readability (simplify) retry was attempted.
    readability_retried: bool = False
    # Optional journey metadata (scan pages + OCR attribution).
    journey: ReportJourneyOut | None = None
    # Which text was used: reference (TCGA-Reports) | our_ocr
    text_source: str = "reference"
    ocr_run_id: int | None = None
    # Glossary terms relevant to this explanation (optional enrichment).
    glossary: list[dict[str, Any]] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Annotation / review
# ---------------------------------------------------------------------------


class GoldLabelSubmit(BaseModel):
    """Gold labels keyed by fact field name."""

    gold_labels: dict[str, FactSpan | None]
    status: Literal["completed"] = "completed"


class AnnotationTaskOut(BaseModel):
    id: int
    batch_id: int
    report_id: int
    assignee_id: int
    status: str
    gold_labels: dict[str, Any] | None = None
    completed_at: datetime | None = None
    # Report text only — never include generation output for annotators.
    report: ReportDetail | None = None

    model_config = {"from_attributes": True}


class ReviewScores(BaseModel):
    accuracy: int = Field(ge=1, le=5)
    completeness: int = Field(ge=1, le=5)
    harm_potential: int = Field(ge=1, le=5)


class ReviewSubmit(BaseModel):
    scores: ReviewScores
    flagged_sentences: list[int] = Field(default_factory=list)
    comments: str | None = None
    status: Literal["completed"] = "completed"


class ReviewTaskOut(BaseModel):
    id: int
    batch_id: int
    generation_id: int
    assignee_id: int
    status: str
    scores: dict[str, Any] | None = None
    flagged_sentences: list[Any] | None = None
    comments: str | None = None
    completed_at: datetime | None = None
    # Clinician sees report + explanation but NOT model/prompt version.
    report_text: str | None = None
    cancer_type: str | None = None
    tcga_barcode: str | None = None
    facts: dict[str, Any] | None = None
    explanation: dict[str, Any] | None = None

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Admin: sets, batches, import, runs
# ---------------------------------------------------------------------------


class EvaluationSetCreate(BaseModel):
    name: str
    cancer_types: list[str] = Field(default_factory=list)
    report_ids: list[int] = Field(default_factory=list)


class EvaluationSetOut(BaseModel):
    id: int
    name: str
    cancer_types: list[Any]
    report_ids: list[Any]
    created_at: datetime

    model_config = {"from_attributes": True}


class TaskBatchCreate(BaseModel):
    name: str
    batch_type: Literal["annotate", "review", "auto_check"]
    evaluation_set_id: int | None = None
    assigned_user_ids: list[int] = Field(default_factory=list)


class TaskBatchOut(BaseModel):
    id: int
    name: str
    batch_type: str
    evaluation_set_id: int | None
    assigned_user_ids: list[Any]
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ImportReportItem(BaseModel):
    tcga_barcode: str
    cancer_type: str
    project_id: str = ""
    report_text: str
    gdc_metadata: dict[str, Any] | None = None
    source: str = "tcga"


class ImportReportsRequest(BaseModel):
    reports: list[ImportReportItem]


class AutoCheckRequest(BaseModel):
    generation_ids: list[int] | None = None  # if None, run on all generations
    batch_id: int | None = None
    evaluation_set_id: int | None = None


class ProgressOut(BaseModel):
    annotation_pending: int
    annotation_completed: int
    review_pending: int
    review_completed: int
    total_reports: int
    total_generations: int


# ---------------------------------------------------------------------------
# Results / metrics
# ---------------------------------------------------------------------------


class MetricWithCI(BaseModel):
    name: str
    value: float
    n: int
    ci_low: float
    ci_high: float
    method: str = "wilson"


class ClinicianScoreSummary(BaseModel):
    """Mean clinician Likert scores (1–5) with simple normal CIs."""

    accuracy: MetricWithCI | None = None
    completeness: MetricWithCI | None = None
    harm_potential: MetricWithCI | None = None
    n_reviews: int = 0


class InterRaterSummary(BaseModel):
    """Pairwise exact agreement when multiple clinicians review the same generation."""

    available: bool = False
    n_items_with_multiple_raters: int = 0
    n_pairs: int = 0
    metric: MetricWithCI | None = None


class FailureExample(BaseModel):
    generation_id: int
    report_id: int
    cancer_type: str | None = None
    check_name: str
    detail: str | None = None


class ResultsSummary(BaseModel):
    metrics: list[MetricWithCI]
    by_cancer_type: dict[str, list[MetricWithCI]] = Field(default_factory=dict)
    # Per-field accuracy when auto-checks include field-level breakdowns.
    by_field: dict[str, list[MetricWithCI]] = Field(default_factory=dict)
    auto_check_runs: int = 0
    generations: int = 0
    gold_annotations: int = 0
    clinician_reviews: int = 0
    clinician_scores: ClinicianScoreSummary | None = None
    inter_rater: InterRaterSummary | None = None
    failure_examples: list[FailureExample] = Field(default_factory=list)
    # Fallback generations are excluded from primary metrics; counted separately.
    fallback_generations: int = 0
    fallback_excluded_from_metrics: bool = True
    # Latest OCR benchmark vs TCGA-Reports (Textract) reference.
    ocr_benchmark: dict[str, Any] | None = None


class OcrRunOut(BaseModel):
    id: int
    report_id: int
    engine: str
    engine_version: str
    model: str | None = None
    text: str
    duration_ms: float | None = None
    estimated_cost_usd: float | None = None
    cer: float | None = None
    wer: float | None = None
    pages: list[dict[str, Any]] = Field(default_factory=list)
    created_at: datetime | None = None
    source: str = "precomputed"  # precomputed | live
    precomputed_at: str | None = None
    precomputed: bool = True


class OcrBenchmarkOut(BaseModel):
    id: int
    engine: str
    engine_version: str
    report_ids: list[Any] = Field(default_factory=list)
    summary: dict[str, Any] = Field(default_factory=dict)
    per_report: list[dict[str, Any]] = Field(default_factory=list)
    created_at: datetime | None = None


class AboutOut(BaseModel):
    title: str
    body: str


class GlossaryTerm(BaseModel):
    term: str
    definition: str
    short: str | None = None
    aliases: list[str] = Field(default_factory=list)


class GlossaryOut(BaseModel):
    terms: list[GlossaryTerm]
