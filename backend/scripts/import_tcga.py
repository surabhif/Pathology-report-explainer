#!/usr/bin/env python3
"""Import TCGA-style pathology reports from a JSON file.

Input JSON format:
[
  {
    "tcga_barcode": "TCGA-A2-A0D0-01A",
    "cancer_type": "BRCA",
    "report_text": "...",
    "project_id": "TCGA-BRCA",   # optional
    "gdc_metadata": {}           # optional
  }
]

Usage:
  python scripts/import_tcga.py path/to/reports.json
  python scripts/import_tcga.py --fetch-gdc path/to/reports.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_ROOT))

from app.db import SessionLocal, init_db
from app.services.gdc import fetch_gdc_case_metadata
from app.services.import_reports import import_report


async def main() -> None:
    parser = argparse.ArgumentParser(description="Import TCGA pathology reports")
    parser.add_argument("json_path", type=Path, help="Path to reports JSON array")
    parser.add_argument(
        "--fetch-gdc",
        action="store_true",
        help="Optionally enrich with live GDC metadata (network)",
    )
    args = parser.parse_args()

    items = json.loads(args.json_path.read_text(encoding="utf-8"))
    if not isinstance(items, list):
        raise SystemExit("JSON root must be a list of report objects")

    init_db()
    db = SessionLocal()
    try:
        count = 0
        for item in items:
            meta = item.get("gdc_metadata")
            if args.fetch_gdc:
                live = await fetch_gdc_case_metadata(item["tcga_barcode"])
                if live:
                    meta = {**(meta or {}), **live}
            import_report(
                db,
                tcga_barcode=item["tcga_barcode"],
                cancer_type=item["cancer_type"],
                report_text=item["report_text"],
                project_id=item.get("project_id"),
                gdc_metadata=meta,
                source=item.get("source", "tcga"),
            )
            count += 1
        print(f"Imported {count} reports.")
    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(main())
