"""Public endpoints: list demo reports + explain (rate-limited)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from slowapi import Limiter
from slowapi.util import get_remote_address
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
    ReportSummary,
)
from app.services.explanation import generate_explanation
from app.services.extraction import extract_facts
from app.services.glossary import load_glossary
from app.services.llm.factory import get_llm_provider
from app.services.reading_level import explanation_text_from_payload, flesch_kincaid_grade

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/public", tags=["public"])

limiter = Limiter(key_func=get_remote_address)


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
    """Extract + explain, caching Generation rows by report/provider/model/prompts."""
    provider = get_llm_provider()
    extract_tag = _active_prompt_tag(db, "extract")
    explain_tag = _active_prompt_tag(db, "explain")

    if use_cache:
        cached = (
            db.query(Generation)
            .filter(
                Generation.report_id == report.id,
                Generation.provider == provider.provider_id(),
                Generation.model == provider.model_id(),
                Generation.prompt_extract_version == extract_tag,
                Generation.prompt_explain_version == explain_tag,
            )
            .order_by(Generation.id.desc())
            .first()
        )
        if cached:
            return cached

    # PHI: log ids/lengths only — never full report text
    logger.info("public.explain report_id=%s chars=%d", report.id, len(report.report_text))

    facts, _ = await extract_facts(report.report_text, provider, prompt_name="extract_v1.txt")
    explanation, _ = await generate_explanation(
        report.report_text, facts, provider, prompt_name="explain_v1.txt"
    )
    rl_orig = flesch_kincaid_grade(report.report_text)
    rl_expl = flesch_kincaid_grade(explanation_text_from_payload(explanation.model_dump()))

    gen = Generation(
        report_id=report.id,
        prompt_extract_version=extract_tag,
        prompt_explain_version=explain_tag,
        model=provider.model_id(),
        provider=provider.provider_id(),
        facts_json=facts.model_dump(),
        explanation_json=explanation.model_dump(),
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
    gen = await run_explain_pipeline(db, report)
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
        glossary=_glossary_for_text(report.report_text, expl_text),
    )
