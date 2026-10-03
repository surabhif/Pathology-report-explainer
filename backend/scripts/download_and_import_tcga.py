#!/usr/bin/env python3
"""Download TCGA_Reports.csv.zip and import filtered reports.

Reproducible import for local/dev use. Does not commit the full CSV.

Usage (from repo root or backend/):
  python backend/scripts/download_and_import_tcga.py --cancer-types BRCA,COAD,LUAD --limit-per-type 20
  python backend/scripts/download_and_import_tcga.py --from-csv /path/to/TCGA_Reports.csv --limit-per-type 10
"""

from __future__ import annotations

import argparse
import csv
import io
import sys
import tempfile
import zipfile
from collections import defaultdict
from pathlib import Path
from urllib.request import urlretrieve

BACKEND_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_ROOT.parent
sys.path.insert(0, str(BACKEND_ROOT))

from app.db import SessionLocal, init_db
from app.services.gdc import project_id_for_cancer
from app.services.import_reports import import_report

# Subset of TCGA tissue-source-site (TSS) codes → project (cancer type).
# Extend this map when enabling more cancer types in config/cancer_types.json.
TSS_TO_CANCER: dict[str, str] = {
    # BRCA
    "A2": "BRCA",
    "A7": "BRCA",
    "AC": "BRCA",
    "AN": "BRCA",
    "AO": "BRCA",
    "AR": "BRCA",
    "B6": "BRCA",
    "BH": "BRCA",
    "C8": "BRCA",
    "D8": "BRCA",
    "E2": "BRCA",
    "E9": "BRCA",
    "EW": "BRCA",
    "GM": "BRCA",
    "OL": "BRCA",
    "S3": "BRCA",
    "3C": "BRCA",
    # COAD
    "A6": "COAD",
    "AA": "COAD",
    "AD": "COAD",
    "AM": "COAD",
    "AU": "COAD",
    "AZ": "COAD",
    "CK": "COAD",
    "CM": "COAD",
    "D5": "COAD",
    "DM": "COAD",
    "F4": "COAD",
    "G4": "COAD",
    "NH": "COAD",
    "QG": "COAD",
    # LUAD
    "05": "LUAD",
    "38": "LUAD",
    "44": "LUAD",
    "49": "LUAD",
    "50": "LUAD",
    "55": "LUAD",
    "67": "LUAD",
    "73": "LUAD",
    "78": "LUAD",
    "86": "LUAD",
    "91": "LUAD",
    "97": "LUAD",
    "MP": "LUAD",
    "NJ": "LUAD",
    # LUSC (optional)
    "18": "LUSC",
    "22": "LUSC",
    "33": "LUSC",
    "34": "LUSC",
    "39": "LUSC",
    "46": "LUSC",
    "56": "LUSC",
    "60": "LUSC",
    "63": "LUSC",
    "66": "LUSC",
    "77": "LUSC",
    "85": "LUSC",
    "90": "LUSC",
    "98": "LUSC",
}

ZIP_URL = (
    "https://github.com/tatonetti-lab/tcga-path-reports/raw/main/TCGA_Reports.csv.zip"
)


def barcode_from_filename(patient_filename: str) -> str:
    return patient_filename.split(".", 1)[0]


def cancer_from_barcode(barcode: str) -> str | None:
    parts = barcode.split("-")
    if len(parts) < 3:
        return None
    return TSS_TO_CANCER.get(parts[1])


def iter_csv_rows(csv_path: Path):
    with csv_path.open(newline="", encoding="utf-8", errors="replace") as f:
        yield from csv.DictReader(f)


def download_zip(dest_dir: Path) -> Path:
    zip_path = dest_dir / "TCGA_Reports.csv.zip"
    print(f"Downloading {ZIP_URL} …")
    urlretrieve(ZIP_URL, zip_path)
    with zipfile.ZipFile(zip_path) as zf:
        zf.extract("TCGA_Reports.csv", path=dest_dir)
    return dest_dir / "TCGA_Reports.csv"


def main() -> None:
    parser = argparse.ArgumentParser(description="Download/import TCGA pathology reports")
    parser.add_argument(
        "--cancer-types",
        default="BRCA,COAD,LUAD",
        help="Comma-separated cancer type codes (default: BRCA,COAD,LUAD)",
    )
    parser.add_argument("--limit-per-type", type=int, default=20)
    parser.add_argument("--from-csv", type=Path, default=None, help="Use existing CSV instead of download")
    parser.add_argument(
        "--export-json",
        type=Path,
        default=None,
        help="Also write selected reports to this JSON path",
    )
    parser.add_argument(
        "--fetch-scans",
        action="store_true",
        help="Cache GDC pathology PDF page images (or OCR facsimile) for each imported report",
    )
    parser.add_argument(
        "--no-facsimile",
        action="store_true",
        help="With --fetch-scans, skip OCR facsimiles when GDC is unavailable",
    )
    args = parser.parse_args()
    wanted = {c.strip().upper() for c in args.cancer_types.split(",") if c.strip()}

    if args.from_csv:
        csv_path = args.from_csv
    else:
        tmp = Path(tempfile.mkdtemp(prefix="tcga_import_"))
        csv_path = download_zip(tmp)

    counts: dict[str, int] = defaultdict(int)
    selected: list[dict] = []

    for row in iter_csv_rows(csv_path):
        fn = row.get("patient_filename") or ""
        text = (row.get("text") or "").strip()
        if not fn or len(text) < 400:
            continue
        barcode = barcode_from_filename(fn)
        ctype = cancer_from_barcode(barcode)
        if ctype is None or ctype not in wanted:
            continue
        if counts[ctype] >= args.limit_per_type:
            continue
        selected.append(
            {
                "tcga_barcode": barcode,
                "cancer_type": ctype,
                "project_id": project_id_for_cancer(ctype),
                "report_text": text,
                "source": "tcga",
                "gdc_metadata": {"patient_filename": fn, "tss_code": barcode.split("-")[1]},
            }
        )
        counts[ctype] += 1
        if all(counts.get(c, 0) >= args.limit_per_type for c in wanted):
            break

    if args.export_json:
        args.export_json.parent.mkdir(parents=True, exist_ok=True)
        import json

        args.export_json.write_text(json.dumps(selected, indent=2), encoding="utf-8")
        print(f"Wrote {len(selected)} reports to {args.export_json}")

    init_db()
    db = SessionLocal()
    try:
        for item in selected:
            report = import_report(
                db,
                tcga_barcode=item["tcga_barcode"],
                cancer_type=item["cancer_type"],
                report_text=item["report_text"],
                project_id=item.get("project_id"),
                gdc_metadata=item.get("gdc_metadata"),
                source="tcga",
            )
            if args.fetch_scans and report is not None:
                import asyncio

                from app.services.scan_assets import ensure_scan_pages_for_barcode

                manifest = asyncio.run(
                    ensure_scan_pages_for_barcode(
                        item["tcga_barcode"],
                        item["report_text"],
                        allow_facsimile=not args.no_facsimile,
                    )
                )
                report.scan_manifest = manifest
                db.commit()
        print(f"Imported {len(selected)} reports: {dict(counts)}")
        if args.fetch_scans:
            print("Cached scan pages under data/scan_cache/ (GDC PDF renders when available).")
    finally:
        db.close()


if __name__ == "__main__":
    main()
