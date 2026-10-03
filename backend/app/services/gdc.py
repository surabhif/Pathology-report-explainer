"""TCGA barcode parsing and optional GDC API metadata lookup.

Barcode format (simplified):
  TCGA-XX-XXXX-01A-...  → project inferred from cancer type config; sample type from 4th segment.
"""

from __future__ import annotations

import json
import logging
import re
from functools import lru_cache
from typing import Any

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

BARCODE_RE = re.compile(
    r"^(TCGA)-([A-Z0-9]{2})-([A-Z0-9]{4})-(\d{2})([A-Z])?(?:-([A-Z0-9]{3}))?(?:-([A-Z0-9]{2}))?",
    re.IGNORECASE,
)


@lru_cache
def load_cancer_types() -> dict[str, Any]:
    path = get_settings().config_dir / "cancer_types.json"
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def parse_tcga_barcode(barcode: str) -> dict[str, Any]:
    """Parse a TCGA barcode into structured fields. Does not call the network."""
    m = BARCODE_RE.match(barcode.strip())
    if not m:
        return {
            "valid": False,
            "barcode": barcode,
            "error": "Unrecognized TCGA barcode format",
        }
    sample_type_code = m.group(4)
    # 01 = primary solid tumor, 11 = solid tissue normal, etc.
    sample_type_map = {
        "01": "Primary Solid Tumor",
        "02": "Recurrent Solid Tumor",
        "03": "Primary Blood Derived Cancer",
        "06": "Metastatic",
        "11": "Solid Tissue Normal",
    }
    return {
        "valid": True,
        "barcode": barcode,
        "project_prefix": m.group(1).upper(),
        "tissue_source_site": m.group(2).upper(),
        "participant": m.group(3).upper(),
        "sample_type_code": sample_type_code,
        "sample_type": sample_type_map.get(sample_type_code, "Unknown"),
        "vial": (m.group(5) or "").upper() or None,
        "portion": m.group(6),
        "analyte": m.group(7),
    }


def project_id_for_cancer(cancer_type: str) -> str:
    cfg = load_cancer_types()
    entry = cfg.get("cancer_types", {}).get(cancer_type.upper())
    if entry:
        return entry.get("project_id", f"TCGA-{cancer_type.upper()}")
    return f"TCGA-{cancer_type.upper()}"


async def fetch_gdc_case_metadata(barcode: str, timeout: float = 15.0) -> dict[str, Any] | None:
    """Optional live GDC API lookup. Returns None on failure (MVP: never blocks import).

    PHI note: only request public TCGA metadata; do not log response bodies in production logs.
    """
    parsed = parse_tcga_barcode(barcode)
    if not parsed.get("valid"):
        return None
    # Use submitter_id prefix TCGA-XX-XXXX
    submitter = f"TCGA-{parsed['tissue_source_site']}-{parsed['participant']}"
    url = "https://api.gdc.cancer.gov/cases"
    filters = {
        "op": "=",
        "content": {"field": "submitter_id", "value": submitter},
    }
    params = {
        "filters": json.dumps(filters),
        "fields": "submitter_id,project.project_id,primary_site,disease_type,diagnoses.tumor_stage",
        "format": "JSON",
        "size": "1",
    }
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
        hits = data.get("data", {}).get("hits", [])
        if not hits:
            logger.info("gdc.no_hit submitter=%s", submitter)
            return {"submitter_id": submitter, "found": False}
        hit = hits[0]
        logger.info("gdc.hit submitter=%s project=%s", submitter, hit.get("project", {}))
        return {"found": True, "case": hit, "parsed_barcode": parsed}
    except Exception as exc:  # noqa: BLE001 — optional enrichment must not fail hard
        logger.warning("gdc.fetch_failed submitter=%s err=%s", submitter, type(exc).__name__)
        return None


def metadata_agrees_with_report(
    gdc_metadata: dict[str, Any] | None,
    cancer_type: str,
) -> dict[str, Any]:
    """Check whether GDC project/cancer type agrees with our stored cancer_type label."""
    expected_project = project_id_for_cancer(cancer_type)
    if not gdc_metadata:
        return {
            "checked": False,
            "agreed": None,
            "expected_project": expected_project,
            "reason": "no_gdc_metadata",
        }
    case = gdc_metadata.get("case") or {}
    project = (case.get("project") or {}).get("project_id") or gdc_metadata.get("project_id")
    if not project:
        # Seeded metadata may store project_id at top level
        project = gdc_metadata.get("project_id")
    agreed = project == expected_project if project else None
    return {
        "checked": project is not None,
        "agreed": agreed,
        "expected_project": expected_project,
        "observed_project": project,
    }
