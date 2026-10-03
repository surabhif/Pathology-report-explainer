"""Import pathology reports (TCGA-style) into the database."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.models import Report
from app.services.gdc import parse_tcga_barcode, project_id_for_cancer

logger = logging.getLogger(__name__)


def import_report(
    db: Session,
    *,
    tcga_barcode: str,
    cancer_type: str,
    report_text: str,
    project_id: str | None = None,
    gdc_metadata: dict[str, Any] | None = None,
    source: str = "tcga",
    upsert: bool = True,
) -> Report:
    """Insert or update a single report. Does not log report_text (PHI-adjacent)."""
    cancer_type = cancer_type.upper()
    project_id = project_id or project_id_for_cancer(cancer_type)
    parsed = parse_tcga_barcode(tcga_barcode)
    meta = dict(gdc_metadata or {})
    meta.setdefault("parsed_barcode", parsed)
    meta.setdefault("project_id", project_id)

    existing = db.query(Report).filter(Report.tcga_barcode == tcga_barcode).first()
    if existing:
        if not upsert:
            return existing
        existing.cancer_type = cancer_type
        existing.project_id = project_id
        existing.report_text = report_text
        existing.gdc_metadata = meta
        existing.source = source
        db.commit()
        db.refresh(existing)
        logger.info("import.updated barcode=%s cancer_type=%s", tcga_barcode, cancer_type)
        return existing

    report = Report(
        tcga_barcode=tcga_barcode,
        cancer_type=cancer_type,
        project_id=project_id,
        report_text=report_text,
        gdc_metadata=meta,
        source=source,
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    logger.info("import.created barcode=%s cancer_type=%s id=%s", tcga_barcode, cancer_type, report.id)
    return report


def import_many(db: Session, items: list[dict[str, Any]]) -> list[Report]:
    return [
        import_report(
            db,
            tcga_barcode=item["tcga_barcode"],
            cancer_type=item["cancer_type"],
            report_text=item["report_text"],
            project_id=item.get("project_id"),
            gdc_metadata=item.get("gdc_metadata"),
            source=item.get("source", "tcga"),
        )
        for item in items
    ]
