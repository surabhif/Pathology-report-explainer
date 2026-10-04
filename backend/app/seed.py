"""Database seed: demo users, sample TCGA-style reports, prompts, rubric, batches.

Sample reports are realistic de-identified pathology language (synthetic — not real patients).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import (
    AnnotationTask,
    EvaluationSet,
    PromptVersion,
    Report,
    ReviewTask,
    Rubric,
    TaskBatch,
    TaskStatus,
    User,
)
from app.routers.public import run_explain_pipeline
from app.services.gdc import project_id_for_cancer

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Sample pathology reports (synthetic / de-identified style)
# ---------------------------------------------------------------------------

BRCA_REPORT_1 = """
SURGICAL PATHOLOGY REPORT
Specimen: Right breast, lumpectomy with sentinel lymph node biopsy
Clinical history: Palpable mass, BI-RADS 5

Gross Description:
The specimen consists of a portion of breast tissue measuring 6.5 x 4.0 x 2.5 cm.
A firm tan-white mass is identified measuring 2.5 cm in greatest dimension.

Microscopic Diagnosis:
Invasive ductal carcinoma, Nottingham histologic grade 2 (tubule 2, nuclear 2, mitotic 2; score 6/9).
Tumor size: 2.5 cm in greatest dimension.
Surgical margins are negative for invasive carcinoma (closest margin 0.4 cm).
Lymphovascular invasion: not identified.
Ductal carcinoma in situ, intermediate grade, present, comprising approximately 10% of tumor.

Lymph nodes: 2 of 15 lymph nodes positive for metastatic carcinoma (sentinel nodes).
Pathologic stage: pT2 N1 M0

Biomarkers (on invasive carcinoma):
ER: positive (95%)
PR: positive (80%)
HER2: negative (1+)
Ki-67: 18%
""".strip()

BRCA_REPORT_2 = """
FINAL DIAGNOSIS — LEFT MASTECTOMY
Procedure: Left total mastectomy and axillary lymph node dissection

Histologic type: Invasive lobular carcinoma.
Histologic grade: Grade 2.
The tumor measures 3.2 cm in greatest dimension.
Surgical margins are negative (uninvolved by invasive carcinoma).
Lymph nodes: 0 of 12 lymph nodes positive for metastasis.
Pathologic stage (pTNM): pT2N0M0

Immunohistochemistry:
ER positive (Allred 8/8)
PR negative
HER2 negative (0)
""".strip()

COAD_REPORT_1 = """
COLONIC RESECTION — PATHOLOGY REPORT
Specimen: Right hemicolectomy

Diagnosis: Moderately differentiated adenocarcinoma arising in a background of tubular adenoma.
Tumor size: measuring 4.1 cm in greatest dimension.
Invasion through muscularis propria into pericolic adipose tissue.
Surgical margins are negative / free of carcinoma.
Lymph nodes: 3 of 18 lymph nodes positive for metastatic adenocarcinoma.
Pathologic stage: pT3 N1 M0

Mismatch repair / biomarkers:
MLH1: retained
MSI: MSI-stable
KRAS: mutant
""".strip()

COAD_REPORT_2 = """
SURGICAL PATHOLOGY — SIGMOID COLON RESECTION
Clinical: Obstructing sigmoid mass

Microscopic: Invasive adenocarcinoma, moderately differentiated.
Greatest dimension of tumor: 2.8 cm.
Margins negative for tumor.
Lymphovascular invasion present.
0 of 14 lymph nodes examined contained metastasis.
Pathologic stage pT2N0M0.

Biomarkers:
MSI: MSI-high
MLH1: lost
KRAS: wild-type
""".strip()

LUAD_REPORT_1 = """
LUNG RESECTION PATHOLOGY REPORT
Specimen: Right upper lobectomy

Diagnosis: Acinar adenocarcinoma of lung.
Histologic grade: Grade 2.
Tumor size: 2.2 cm in greatest dimension.
Visceral pleural invasion: not identified.
Surgical margins are negative.
Lymph nodes: 1 of 10 lymph nodes positive for metastatic adenocarcinoma.
Pathologic stage: pT1c N1 M0

Molecular / biomarkers:
EGFR: mutant
ALK: negative
PD-L1: TPS 40%
""".strip()

LUAD_REPORT_2 = """
FINAL DIAGNOSIS — LEFT LOWER LOBE WEDGE RESECTION
Tumor type: Invasive adenocarcinoma (predominantly lepidic with acinar patterns).
Grade: Grade 1 (well differentiated).
The tumor measures 1.4 cm in greatest dimension.
Margins negative / uninvolved by carcinoma.
Lymph nodes: 0 of 5 lymph nodes positive.
Pathologic stage: pT1b N0 M0

Biomarkers:
EGFR: wild-type
KRAS: mutant
PD-L1: negative (TPS <1%)
ALK: negative
""".strip()

SAMPLE_REPORTS = [
    {
        "tcga_barcode": "TCGA-A2-A0D0-01A",
        "cancer_type": "BRCA",
        "report_text": BRCA_REPORT_1,
        "gdc_metadata": {
            "project_id": "TCGA-BRCA",
            "primary_site": "Breast",
            "disease_type": "Ductal and Lobular Neoplasms",
            "found": True,
        },
    },
    {
        "tcga_barcode": "TCGA-E2-A14N-01A",
        "cancer_type": "BRCA",
        "report_text": BRCA_REPORT_2,
        "gdc_metadata": {
            "project_id": "TCGA-BRCA",
            "primary_site": "Breast",
            "disease_type": "Ductal and Lobular Neoplasms",
            "found": True,
        },
    },
    {
        "tcga_barcode": "TCGA-A6-2671-01A",
        "cancer_type": "COAD",
        "report_text": COAD_REPORT_1,
        "gdc_metadata": {
            "project_id": "TCGA-COAD",
            "primary_site": "Colorectal",
            "disease_type": "Adenomas and Adenocarcinomas",
            "found": True,
        },
    },
    {
        "tcga_barcode": "TCGA-CM-4743-01A",
        "cancer_type": "COAD",
        "report_text": COAD_REPORT_2,
        "gdc_metadata": {
            "project_id": "TCGA-COAD",
            "primary_site": "Colorectal",
            "disease_type": "Adenomas and Adenocarcinomas",
            "found": True,
        },
    },
    {
        "tcga_barcode": "TCGA-05-4244-01A",
        "cancer_type": "LUAD",
        "report_text": LUAD_REPORT_1,
        "gdc_metadata": {
            "project_id": "TCGA-LUAD",
            "primary_site": "Lung",
            "disease_type": "Adenomas and Adenocarcinomas",
            "found": True,
        },
    },
    {
        "tcga_barcode": "TCGA-44-6146-01A",
        "cancer_type": "LUAD",
        "report_text": LUAD_REPORT_2,
        "gdc_metadata": {
            "project_id": "TCGA-LUAD",
            "primary_site": "Lung",
            "disease_type": "Adenomas and Adenocarcinomas",
            "found": True,
        },
    },
]

DEMO_USER_TEMPLATES = [
    {
        "email": "surabhi@example.com",
        "name": "Surabhi Admin",
        "role": "admin",
        "token_attr": "demo_admin_token",
        "local_default": "DEMO_ADMIN_TOKEN",
    },
    {
        "email": "annotator@example.com",
        "name": "Demo Annotator",
        "role": "annotator",
        "token_attr": "demo_annotator_token",
        "local_default": "DEMO_ANNOTATOR_TOKEN",
    },
    {
        "email": "clinician@example.com",
        "name": "Demo Clinician",
        "role": "clinician",
        "token_attr": "demo_clinician_token",
        "local_default": "DEMO_CLINICIAN_TOKEN",
    },
]


def _resolve_demo_users() -> list[dict] | None:
    """Build demo user seed rows from env, or skip in production without tokens.

    - If DEMO_*_TOKEN env vars are set, use those values.
    - In production/prod: never seed the well-known DEMO_* defaults; skip if unset.
    - In development: fall back to local convenience defaults for one-command demos.
    """
    settings = get_settings()
    from_env: list[dict] = []
    missing = 0
    for tmpl in DEMO_USER_TEMPLATES:
        token = getattr(settings, tmpl["token_attr"], "").strip()
        if token:
            from_env.append(
                {
                    "email": tmpl["email"],
                    "name": tmpl["name"],
                    "role": tmpl["role"],
                    "invite_token": token,
                }
            )
        else:
            missing += 1

    if from_env and missing == 0:
        return from_env

    if from_env and missing:
        logger.warning(
            "seed.demo_tokens partial: set all of DEMO_ADMIN_TOKEN, "
            "DEMO_ANNOTATOR_TOKEN, DEMO_CLINICIAN_TOKEN — skipping demo users"
        )
        return None

    if settings.is_production:
        logger.info(
            "seed.demo_users skipped in production (set DEMO_*_TOKEN env vars to seed)"
        )
        return None

    # Local / test convenience defaults — never used when APP_ENV=production.
    return [
        {
            "email": t["email"],
            "name": t["name"],
            "role": t["role"],
            "invite_token": t["local_default"],
        }
        for t in DEMO_USER_TEMPLATES
    ]


def _seed_users(db: Session) -> dict[str, User]:
    specs = _resolve_demo_users()
    if not specs:
        return {}
    by_role: dict[str, User] = {}
    for u in specs:
        existing = db.query(User).filter(User.email == u["email"]).first()
        if existing:
            # Keep invite token in sync with env when re-seeding.
            if u.get("invite_token") and existing.invite_token != u["invite_token"]:
                existing.invite_token = u["invite_token"]
            by_role[u["role"]] = existing
            continue
        user = User(**u)
        db.add(user)
        db.flush()
        by_role[u["role"]] = user
    db.commit()
    return by_role


def _seed_prompts(db: Session) -> None:
    settings = get_settings()
    for kind, filename in [("extract", "extract_v1.txt"), ("explain", "explain_v1.txt")]:
        path: Path = settings.prompts_dir / filename
        content = path.read_text(encoding="utf-8") if path.exists() else f"# {kind} prompt v1\n"
        existing = (
            db.query(PromptVersion)
            .filter(PromptVersion.kind == kind, PromptVersion.version == "1")
            .first()
        )
        if existing:
            continue
        # Deactivate others of same kind
        for row in db.query(PromptVersion).filter(PromptVersion.kind == kind).all():
            row.is_active = False
        db.add(
            PromptVersion(
                name=filename.replace(".txt", ""),
                version="1",
                kind=kind,
                content=content,
                is_active=True,
            )
        )
    db.commit()


def _seed_rubric(db: Session) -> None:
    settings = get_settings()
    path = settings.config_dir / "rubric.json"
    content = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"version": "1"}
    if db.query(Rubric).filter(Rubric.version == "1").first():
        return
    for row in db.query(Rubric).all():
        row.is_active = False
    db.add(Rubric(version="1", content=content, is_active=True))
    db.commit()


def _sample_reports_for_seed() -> list[dict]:
    """Prefer real TCGA-Reports excerpts from data/sample_reports.json when present."""
    from app.config import get_settings

    sample_path = Path(get_settings().data_dir) / "sample_reports.json"
    if sample_path.exists():
        try:
            items = json.loads(sample_path.read_text(encoding="utf-8"))
            out = []
            for item in items:
                ctype = item.get("cancer_type")
                if ctype not in {"BRCA", "COAD", "LUAD"}:
                    continue
                out.append(
                    {
                        "tcga_barcode": item["tcga_barcode"],
                        "cancer_type": ctype,
                        "report_text": item["report_text"],
                        "gdc_metadata": {
                            **(item.get("gdc_metadata") or {}),
                            "project_id": item.get("project_id") or f"TCGA-{ctype}",
                            "found": True,
                            "from_sample_reports_json": True,
                        },
                    }
                )
            if out:
                return out
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("seed.sample_reports_json_failed err=%s", type(exc).__name__)
    return SAMPLE_REPORTS


def _seed_reports(db: Session) -> list[Report]:
    from app.services.scan_assets import load_manifest

    reports: list[Report] = []
    for item in _sample_reports_for_seed():
        existing = db.query(Report).filter(Report.tcga_barcode == item["tcga_barcode"]).first()
        if existing:
            # Refresh OCR text / scan manifest on re-seed without wiping ids.
            if item.get("report_text") and existing.report_text != item["report_text"]:
                # Keep existing synthetic rows stable if already present from older seeds.
                pass
            manifest = load_manifest(existing.tcga_barcode)
            if manifest:
                existing.scan_manifest = manifest
            reports.append(existing)
            continue
        manifest = load_manifest(item["tcga_barcode"])
        r = Report(
            tcga_barcode=item["tcga_barcode"],
            cancer_type=item["cancer_type"],
            project_id=project_id_for_cancer(item["cancer_type"]),
            report_text=item["report_text"],
            gdc_metadata=item["gdc_metadata"],
            scan_manifest=manifest,
            source="tcga",
        )
        db.add(r)
        db.flush()
        reports.append(r)
    db.commit()
    return reports


async def _seed_batches_and_generations(db: Session, users: dict[str, User], reports: list[Report]) -> None:
    if db.query(EvaluationSet).count() > 0:
        return

    eset = EvaluationSet(
        name="MVP Demo Evaluation Set",
        cancer_types=["BRCA", "COAD", "LUAD"],
        report_ids=[r.id for r in reports],
    )
    db.add(eset)
    db.commit()
    db.refresh(eset)

    # Generate explanations with mock for all reports (for review batch)
    generations = []
    for report in reports:
        gen = await run_explain_pipeline(db, report)
        generations.append(gen)

    annotate_batch = TaskBatch(
        name="MVP Annotate Batch",
        batch_type="annotate",
        evaluation_set_id=eset.id,
        assigned_user_ids=[users["annotator"].id],
        status="active",
    )
    db.add(annotate_batch)
    db.commit()
    db.refresh(annotate_batch)

    for report in reports:
        db.add(
            AnnotationTask(
                batch_id=annotate_batch.id,
                report_id=report.id,
                assignee_id=users["annotator"].id,
                status=TaskStatus.pending.value,
            )
        )

    review_batch = TaskBatch(
        name="MVP Review Batch",
        batch_type="review",
        evaluation_set_id=eset.id,
        assigned_user_ids=[users["clinician"].id],
        status="active",
    )
    db.add(review_batch)
    db.commit()
    db.refresh(review_batch)

    for gen in generations:
        db.add(
            ReviewTask(
                batch_id=review_batch.id,
                generation_id=gen.id,
                assignee_id=users["clinician"].id,
                status=TaskStatus.pending.value,
            )
        )
    db.commit()
    logger.info(
        "seed.batches annotate=%s review=%s generations=%d",
        annotate_batch.id,
        review_batch.id,
        len(generations),
    )


async def seed_all(db: Session) -> None:
    """Idempotent seed for MVP startup."""
    logger.info("seed.start")
    users = _seed_users(db)
    _seed_prompts(db)
    _seed_rubric(db)
    reports = _seed_reports(db)
    _seed_precomputed_ocr(db, reports)
    _seed_ocr_benchmark(db)
    if users.get("annotator") and users.get("clinician"):
        await _seed_batches_and_generations(db, users, reports)
    else:
        logger.info("seed.batches skipped (demo annotator/clinician not seeded)")
    logger.info("seed.done users=%d reports=%d", len(users), len(reports))


def _seed_precomputed_ocr(db: Session, reports: list[Report]) -> None:
    """Attach committed disk-cache OCR to each report (no live Tesseract)."""
    from app.services.ocr.pipeline import ensure_precomputed_ocr_run

    n = 0
    for report in reports:
        run = ensure_precomputed_ocr_run(db, report, engine="tesseract")
        if run:
            n += 1
    logger.info("seed.precomputed_ocr runs=%d / reports=%d", n, len(reports))


def _seed_ocr_benchmark(db: Session) -> None:
    """Ensure Results shows the committed n=30 real-scan OCR benchmark."""
    from app.services.ocr.benchmark_import import ensure_ocr_benchmark_seeded

    run = ensure_ocr_benchmark_seeded(db)
    if run:
        summary = (run.results_json or {}).get("summary") or {}
        logger.info(
            "seed.ocr_benchmark id=%s n_real=%s",
            run.id,
            summary.get("n_real_scans_scored"),
        )
