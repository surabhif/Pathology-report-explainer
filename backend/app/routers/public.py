"""Public endpoints: list demo reports + explain (rate-limited)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from slowapi import Limiter
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models import Generation, OcrRun, PromptVersion, Report
from app.schemas import (
    ExplainResponse,
    ExplanationPayload,
    FactSheet,
    GlossaryOut,
    GlossaryTerm,
    OcrDiffOut,
    OcrRunOut,
    OurOcrOut,
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
from app.services.ocr.metrics import ocr_error_metrics, word_diff_spans
from app.services.ocr.pipeline import latest_ocr_run
from app.services.rate_limit import client_ip_key
from app.services.reading_level import explanation_text_from_payload, flesch_kincaid_grade
from app.services.scan_assets import case_cache_dir, is_real_scan_manifest, load_manifest

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


async def run_explain_pipeline(
    db: Session,
    report: Report,
    *,
    use_cache: bool = True,
    text_source: str = "reference",
    ocr_run: OcrRun | None = None,
) -> Generation:
    """Extract + explain, caching Generation rows by report/provider/model/prompts/text_source.

    Fallback generations are stored with provider=mock and is_fallback=True so
    research evaluation never misattributes heuristic output to a hosted model.
    """
    text_source = (text_source or "reference").strip().lower()
    if text_source not in {"reference", "our_ocr"}:
        text_source = "reference"

    source_text = report.report_text
    ocr_run_id: int | None = None
    if text_source == "our_ocr":
        if ocr_run is None:
            ocr_run = latest_ocr_run(db, report.id)
        if ocr_run is None:
            raise HTTPException(
                400,
                "No PathExplain OCR run yet. Call /api/public/reports/{id}/ocr first.",
            )
        source_text = ocr_run.text
        ocr_run_id = ocr_run.id

    provider = get_llm_provider()
    extract_tag = _active_prompt_tag(db, "extract")
    explain_tag = _active_prompt_tag(db, "explain")
    requested_provider = provider.provider_id()
    requested_model = provider.model_id()

    if use_cache:
        cached_q = (
            db.query(Generation)
            .filter(
                Generation.report_id == report.id,
                Generation.provider == requested_provider,
                Generation.model == requested_model,
                Generation.prompt_extract_version == extract_tag,
                Generation.prompt_explain_version == explain_tag,
                Generation.is_fallback.is_(False),
                Generation.text_source == text_source,
            )
        )
        if ocr_run_id is not None:
            cached_q = cached_q.filter(Generation.ocr_run_id == ocr_run_id)
        cached = cached_q.order_by(Generation.id.desc()).first()
        if cached:
            return cached

    # PHI: log ids/lengths only — never full report text
    logger.info(
        "public.explain report_id=%s chars=%d text_source=%s",
        report.id,
        len(source_text),
        text_source,
    )

    extract_res = await extract_facts(source_text, provider, prompt_name="extract_v1.txt")
    explain_res = await generate_explanation(
        source_text,
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

    rl_orig = flesch_kincaid_grade(source_text)
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
        text_source=text_source,
        ocr_run_id=ocr_run_id,
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


def _ocr_source_fields(run: OcrRun) -> tuple[str, str | None, bool]:
    meta = run.meta_json or {}
    precomputed = bool(meta.get("precomputed", True))
    source = "precomputed" if precomputed else "live"
    precomputed_at = meta.get("precomputed_at")
    if precomputed_at is None and precomputed and run.created_at:
        precomputed_at = run.created_at.isoformat()
    return source, precomputed_at, precomputed


def _our_ocr_out(run: OcrRun) -> OurOcrOut:
    pages = run.pages_json or []
    source, precomputed_at, precomputed = _ocr_source_fields(run)
    if precomputed:
        note = (
            f"Precomputed PathExplain OCR ({run.engine} / {run.engine_version}"
            + (f", generated {precomputed_at}" if precomputed_at else "")
            + "). Generated offline — visitors never trigger live Tesseract."
        )
        label = "Our OCR (precomputed)"
    else:
        note = (
            f"Live PathExplain OCR ({run.engine} / {run.engine_version}). "
            "Admin-triggered on this instance."
        )
        label = "Our OCR (live)"
    return OurOcrOut(
        ocr_run_id=run.id,
        engine=run.engine,
        engine_version=run.engine_version,
        model=run.model,
        text=run.text,
        duration_ms=run.duration_ms,
        estimated_cost_usd=run.estimated_cost_usd,
        cer=run.cer,
        wer=run.wer,
        page_count=len(pages),
        source=source,
        precomputed_at=precomputed_at,
        label=label,
        note=note,
    )


def _ocr_run_out(run: OcrRun) -> OcrRunOut:
    source, precomputed_at, precomputed = _ocr_source_fields(run)
    return OcrRunOut(
        id=run.id,
        report_id=run.report_id,
        engine=run.engine,
        engine_version=run.engine_version,
        model=run.model,
        text=run.text,
        duration_ms=run.duration_ms,
        estimated_cost_usd=run.estimated_cost_usd,
        cer=run.cer,
        wer=run.wer,
        pages=list(run.pages_json or []),
        created_at=run.created_at,
        source=source,
        precomputed_at=precomputed_at,
        precomputed=precomputed,
    )


def _journey_for_report(report: Report, db: Session | None = None) -> ReportJourneyOut:
    settings = get_settings()
    manifest = report.scan_manifest or load_manifest(report.tcga_barcode) or {}
    real = is_real_scan_manifest(manifest)
    pages_out: list[ScanPageOut] = []
    # Never expose facsimile pages as "scans" in the public demo.
    if real:
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
    our: OurOcrOut | None = None
    if db is not None:
        # Prefer committed precomputed OCR — never kick off live Tesseract here.
        from app.services.ocr.pipeline import get_precomputed_ocr

        run = get_precomputed_ocr(db, report, engine=settings.ocr_engine)
        if run:
            our = _our_ocr_out(run)
    return ReportJourneyOut(
        report_id=report.id,
        tcga_barcode=report.tcga_barcode,
        cancer_type=report.cancer_type,
        scan_source=manifest.get("source") if real else None,
        scan_label=manifest.get("label") if real else None,
        scan_citation=manifest.get("citation") if real else None,
        scan_pages=pages_out,
        report_text=report.report_text,
        our_ocr=our,
        default_ocr_engine=settings.ocr_engine,
        has_real_scan=real,
        scan_scorable=real,
        explain_path=f"/api/public/reports/{report.id}/explain",
    )


@router.get("/reports/{report_id}/journey", response_model=ReportJourneyOut)
def report_journey(report_id: int, db: Session = Depends(get_db)) -> ReportJourneyOut:
    """Stage metadata for scan → OCR text → PathExplain facts/explanation."""
    report = db.query(Report).filter(Report.id == report_id).first()
    if not report:
        raise HTTPException(404, "Report not found")
    return _journey_for_report(report, db)


@router.get("/reports/{report_id}/ocr", response_model=OcrRunOut)
@limiter.limit(get_settings().rate_limit_explain)
async def report_ocr(
    request: Request,
    report_id: int,
    db: Session = Depends(get_db),
    engine: str | None = None,
) -> OcrRunOut:
    """Return **precomputed** PathExplain OCR for a demo report.

    Live / forced Tesseract is admin-only (``POST /api/admin/ocr/run``) so
    Render free-tier visitors never block the event loop or OOM the instance.
    """
    from app.services.ocr.pipeline import get_precomputed_ocr

    report = db.query(Report).filter(Report.id == report_id).first()
    if not report:
        raise HTTPException(404, "Report not found")
    run = get_precomputed_ocr(db, report, engine=engine)
    if not run:
        raise HTTPException(
            404,
            "No precomputed OCR for this report. "
            "Public demo does not run live Tesseract — ask an admin to import "
            "or generate offline OCR.",
        )
    return _ocr_run_out(run)


@router.get("/reports/{report_id}/ocr/diff", response_model=OcrDiffOut)
async def report_ocr_diff(
    report_id: int,
    db: Session = Depends(get_db),
    engine: str | None = None,
) -> OcrDiffOut:
    """Word-level diff between TCGA-Reports reference text and our OCR."""
    import asyncio

    report = db.query(Report).filter(Report.id == report_id).first()
    if not report:
        raise HTTPException(404, "Report not found")
    run = latest_ocr_run(db, report.id, engine=engine) or latest_ocr_run(db, report.id)
    if not run:
        raise HTTPException(404, "No OCR run yet — call /ocr first")
    diff = await asyncio.to_thread(word_diff_spans, report.report_text, run.text)
    # Prefer stored CER/WER — do not recompute on the request path.
    cer = run.cer
    wer = run.wer
    if cer is None or wer is None:
        metrics = await asyncio.to_thread(ocr_error_metrics, report.report_text, run.text)
        cer = metrics["cer"]
        wer = metrics["wer"]
    return OcrDiffOut(ops=diff["ops"], changed=diff["changed"], cer=cer, wer=wer)


@router.get("/reports/{report_id}/scan-pages/{filename}")
def report_scan_page(report_id: int, filename: str, db: Session = Depends(get_db)):
    """Serve a cached authentic scan page image (never hot-link GDC/S3 at runtime).

    Facsimile pages are not served on the public demo — they are circular vs Textract.
    """
    from fastapi.responses import FileResponse

    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(400, "Invalid filename")
    report = db.query(Report).filter(Report.id == report_id).first()
    if not report:
        raise HTTPException(404, "Report not found")
    manifest = report.scan_manifest or load_manifest(report.tcga_barcode)
    if not is_real_scan_manifest(manifest):
        raise HTTPException(404, "No authentic scan page cached for this report")
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
    text_source: str = "reference",
    ocr_engine: str | None = None,
) -> ExplainResponse:
    """Run (or return cached) extraction + explanation pipeline.

    text_source=reference uses TCGA-Reports (Textract) text.
    text_source=our_ocr runs/uses PathExplain OCR first, then grounds quotes in that text.
    """
    report = db.query(Report).filter(Report.id == report_id).first()
    if not report:
        raise HTTPException(404, "Report not found")

    ocr_run = None
    source = (text_source or "reference").strip().lower()
    if source == "our_ocr":
        try:
            # Public explain grounds in precomputed OCR only — never live Tesseract.
            from app.services.ocr.pipeline import get_precomputed_ocr

            ocr_run = get_precomputed_ocr(db, report, engine=ocr_engine)
            if ocr_run is None:
                raise FileNotFoundError(
                    "No precomputed OCR for this report; cannot explain from Our OCR."
                )
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        except LLMServiceError as exc:
            status = 504 if "timeout" in exc.code else 502
            raise HTTPException(
                status_code=status, detail={"message": exc.message, "code": exc.code}
            ) from exc

    try:
        gen = await run_explain_pipeline(
            db, report, text_source=source, ocr_run=ocr_run
        )
    except LLMServiceError as exc:
        # Clear, UI-displayable error — not a generic 500.
        status = 504 if exc.code == "llm_timeout" else 502
        raise HTTPException(
            status_code=status,
            detail={"message": exc.message, "code": exc.code},
        ) from exc
    except HTTPException:
        raise

    facts = FactSheet.model_validate(gen.facts_json)
    explanation = ExplanationPayload.model_validate(gen.explanation_json)
    expl_text = " ".join(s.sentence for s in explanation.sentences)
    used_text = ocr_run.text if ocr_run is not None else report.report_text
    return ExplainResponse(
        report_id=report.id,
        generation_id=gen.id,
        report_text=used_text,
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
        glossary=_glossary_for_text(used_text, expl_text),
        journey=_journey_for_report(report, db),
        text_source=gen.text_source or "reference",
        ocr_run_id=gen.ocr_run_id,
    )
