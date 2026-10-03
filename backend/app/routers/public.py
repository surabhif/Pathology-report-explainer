"""Public endpoints: list demo reports + explain (rate-limited)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from slowapi import Limiter
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models import Generation, PromptVersion, Report
from app.schemas import (
    ExplainResponse,
    ExplanationPayload,
    FactSheet,
    GlossaryOut,
    GlossaryTerm,
    ReportDetail,
    ReportJourneyOut,
    ReportSummary,
    ScanPageOut,
)
from app.services.explanation import generate_explanation
from app.services.extraction import extract_facts
from app.services.glossary import load_glossary
from app.services.llm.errors import LLMServiceError
from app.services.llm.factory import get_llm_provider
from app.services.rate_limit import client_ip_key
from app.services.reading_level import explanation_text_from_payload, flesch_kincaid_grade
from app.services.scan_assets import case_cache_dir, load_manifest

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/public", tags=["public"])

limiter = Limiter(key_func=client_ip_key)


def _active_prompt_tag(db: Session, kind: str) -> str:
    row = (
        db.query(PromptVersion)
        .filter(PromptVersion.kind == kind, PromptVersion.is_active.is_(True))
        .order_by(PromptVersion.id.desc())
        .first()
    )
    if row:
        return f"{row.name}_v{row.version}" if not row.name.endswith(row.version) else row.name
    return f"{kind}_v1"


async def run_explain_pipeline(db: Session, report: Report, *, use_cache: bool = True) -> Generation:
    """Extract + explain, caching Generation rows by report/provider/model/prompts.

    Fallback generations are stored with provider=mock and is_fallback=True so
    research evaluation never misattributes heuristic output to a hosted model.
    """
    provider = get_llm_provider()
    extract_tag = _active_prompt_tag(db, "extract")
    explain_tag = _active_prompt_tag(db, "explain")
    requested_provider = provider.provider_id()
    requested_model = provider.model_id()

    if use_cache:
        cached = (
            db.query(Generation)
            .filter(
                Generation.report_id == report.id,
                Generation.provider == requested_provider,
                Generation.model == requested_model,
                Generation.prompt_extract_version == extract_tag,
                Generation.prompt_explain_version == explain_tag,
                Generation.is_fallback.is_(False),
            )
            .order_by(Generation.id.desc())
            .first()
        )
        if cached:
            return cached

    # PHI: log ids/lengths only — never full report text
    logger.info("public.explain report_id=%s chars=%d", report.id, len(report.report_text))

    extract_res = await extract_facts(report.report_text, provider, prompt_name="extract_v1.txt")
    explain_res = await generate_explanation(
        report.report_text,
        extract_res.facts,
        provider,
        prompt_name="explain_v1.txt",
        force_heuristic=extract_res.used_fallback,
    )

    used_fallback = extract_res.used_fallback or explain_res.used_fallback
    fallback_reason = extract_res.fallback_reason or explain_res.fallback_reason
    # Honest labeling: fallback output is mock, not the requested hosted model.
    stored_provider = "mock" if used_fallback else requested_provider
    stored_model = "mock-heuristic-v1" if used_fallback else requested_model

    rl_orig = flesch_kincaid_grade(report.report_text)
    rl_expl = flesch_kincaid_grade(
        explanation_text_from_payload(explain_res.explanation.model_dump())
    )

    gen = Generation(
        report_id=report.id,
        prompt_extract_version=extract_tag,
        prompt_explain_version=explain_tag,
        model=stored_model,
        provider=stored_provider,
        is_fallback=used_fallback,
        fallback_reason=fallback_reason,
        requested_provider=requested_provider if used_fallback else None,
        requested_model=requested_model if used_fallback else None,
        explanation_retried=bool(explain_res.retried),
        grounding_check_json=explain_res.grounding_check or None,
        facts_json=extract_res.facts.model_dump(),
        explanation_json=explain_res.explanation.model_dump(),
        reading_level_original=rl_orig,
        reading_level_explanation=rl_expl,
    )
    db.add(gen)
    db.commit()
    db.refresh(gen)
    return gen


@router.get("/reports", response_model=list[ReportSummary])
def list_reports(db: Session = Depends(get_db), cancer_type: str | None = None) -> list[ReportSummary]:
    q = db.query(Report)
    if cancer_type:
        q = q.filter(Report.cancer_type == cancer_type.upper())
    rows = q.order_by(Report.id).all()
    return [ReportSummary.model_validate(r) for r in rows]


@router.get("/reports/{report_id}", response_model=ReportDetail)
def get_report(report_id: int, db: Session = Depends(get_db)) -> ReportDetail:
    """Return a demo report including text (needed for quote highlighting)."""
    report = db.query(Report).filter(Report.id == report_id).first()
    if not report:
        raise HTTPException(404, "Report not found")
    return ReportDetail.model_validate(report)


def _journey_for_report(report: Report) -> ReportJourneyOut:
    manifest = report.scan_manifest or load_manifest(report.tcga_barcode) or {}
    pages_out: list[ScanPageOut] = []
    for p in manifest.get("pages") or []:
        filename = p.get("filename")
        if not filename:
            continue
        pages_out.append(
            ScanPageOut(
                page=int(p.get("page") or len(pages_out) + 1),
                url=f"/api/public/reports/{report.id}/scan-pages/{filename}",
                width=p.get("width"),
                height=p.get("height"),
            )
        )
    return ReportJourneyOut(
        report_id=report.id,
        tcga_barcode=report.tcga_barcode,
        cancer_type=report.cancer_type,
        scan_source=manifest.get("source"),
        scan_label=manifest.get("label"),
        scan_citation=manifest.get("citation"),
        scan_pages=pages_out,
        report_text=report.report_text,
        explain_path=f"/api/public/reports/{report.id}/explain",
    )


@router.get("/reports/{report_id}/journey", response_model=ReportJourneyOut)
def report_journey(report_id: int, db: Session = Depends(get_db)) -> ReportJourneyOut:
    """Stage metadata for scan → OCR text → PathExplain facts/explanation."""
    report = db.query(Report).filter(Report.id == report_id).first()
    if not report:
        raise HTTPException(404, "Report not found")
    return _journey_for_report(report)


@router.get("/reports/{report_id}/scan-pages/{filename}")
def report_scan_page(report_id: int, filename: str, db: Session = Depends(get_db)):
    """Serve a cached scan/facsimile page image (never hot-link GDC at runtime)."""
    from fastapi.responses import FileResponse

    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(400, "Invalid filename")
    report = db.query(Report).filter(Report.id == report_id).first()
    if not report:
        raise HTTPException(404, "Report not found")
    path = case_cache_dir(report.tcga_barcode) / filename
    if not path.exists():
        raise HTTPException(404, "Scan page not cached")
    media = "image/jpeg" if path.suffix.lower() in {".jpg", ".jpeg"} else "image/png"
    return FileResponse(path, media_type=media)


@router.get("/glossary", response_model=GlossaryOut)
def get_glossary() -> GlossaryOut:
    """Public glossary of pathology terms used in the demo UI."""
    raw = load_glossary()
    terms = [
        GlossaryTerm(
            term=t.get("term", ""),
            definition=t.get("definition", ""),
            short=t.get("short"),
            aliases=list(t.get("aliases") or []),
        )
        for t in raw.get("terms", [])
        if t.get("term")
    ]
    return GlossaryOut(terms=terms)


def _glossary_for_text(*texts: str) -> list[dict]:
    """Pick glossary entries whose term/alias appears in any of the texts."""
    blob = " ".join(t for t in texts if t).lower()
    raw = load_glossary()
    matched: list[dict] = []
    for entry in raw.get("terms", []):
        candidates = [entry.get("term", ""), *(entry.get("aliases") or [])]
        if any(c and c.lower() in blob for c in candidates):
            matched.append(
                {
                    "term": entry.get("term"),
                    "definition": entry.get("definition"),
                    "short": entry.get("short"),
                    "aliases": entry.get("aliases") or [],
                }
            )
    return matched


@router.get("/reports/{report_id}/explain", response_model=ExplainResponse)
@limiter.limit(get_settings().rate_limit_explain)
async def explain_report(
    request: Request,
    report_id: int,
    db: Session = Depends(get_db),
) -> ExplainResponse:
    """Run (or return cached) extraction + explanation pipeline.

    Rate-limited via slowapi. Note: use explicit Depends(get_db) here because
    the limiter decorator can strip Annotated dependency aliases.
    """
    report = db.query(Report).filter(Report.id == report_id).first()
    if not report:
        raise HTTPException(404, "Report not found")
    try:
        gen = await run_explain_pipeline(db, report)
    except LLMServiceError as exc:
        # Clear, UI-displayable error — not a generic 500.
        status = 504 if exc.code == "llm_timeout" else 502
        raise HTTPException(
            status_code=status,
            detail={"message": exc.message, "code": exc.code},
        ) from exc
    facts = FactSheet.model_validate(gen.facts_json)
    explanation = ExplanationPayload.model_validate(gen.explanation_json)
    expl_text = " ".join(s.sentence for s in explanation.sentences)
    return ExplainResponse(
        report_id=report.id,
        generation_id=gen.id,
        report_text=report.report_text,
        facts=facts,
        explanation=explanation,
        reading_level_original=gen.reading_level_original,
        reading_level_explanation=gen.reading_level_explanation,
        provider=gen.provider,
        model=gen.model,
        is_fallback=bool(gen.is_fallback),
        fallback_reason=gen.fallback_reason,
        requested_provider=gen.requested_provider,
        requested_model=gen.requested_model,
        explanation_retried=bool(gen.explanation_retried),
        grounding_check=gen.grounding_check_json,
        glossary=_glossary_for_text(report.report_text, expl_text),
        journey=_journey_for_report(report),
    )
