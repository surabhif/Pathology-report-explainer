#!/usr/bin/env python3
"""Fetch real TCGA pathology page images via HTTP range requests (never full 24GB zip).

Primary: Tatonetti lab Textract input images
  https://tatonettilab-resources.s3.us-west-1.amazonaws.com/tcga-path-reports/imgs_for_aws.zip
Fallback: NCI GDC Pathology Report PDFs (when GDC is up).

Facsimiles are NOT written by default (circular for OCR benchmarks).

Usage:
  python backend/scripts/fetch_scan_pages.py --from-sample-data --force
  python backend/scripts/fetch_scan_pages.py --from-json data/ocr_benchmark_set.json --force
  python backend/scripts/fetch_scan_pages.py --barcode TCGA-B6-A401 --force
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_ROOT.parent
sys.path.insert(0, str(BACKEND_ROOT))

from app.db import SessionLocal, init_db
from app.models import Report
from app.services.scan_assets import (
    ensure_scan_pages_for_barcode,
    is_real_scan_manifest,
    load_manifest,
)


async def cache_one(
    barcode: str,
    text: str,
    *,
    force: bool,
    allow_facsimile: bool,
    prefer_tatonetti: bool,
) -> dict:
    manifest = await ensure_scan_pages_for_barcode(
        barcode,
        text,
        allow_facsimile=allow_facsimile,
        prefer_tatonetti=prefer_tatonetti,
        force=force,
    )
    real = is_real_scan_manifest(manifest)
    print(
        f"{barcode}: source={manifest.get('source')} pages={len(manifest.get('pages') or [])} "
        f"real_scan={real}"
    )
    return manifest


async def main() -> None:
    parser = argparse.ArgumentParser(description="Cache real TCGA pathology scan pages")
    parser.add_argument("--barcode", help="Single TCGA barcode / case id")
    parser.add_argument("--text-file", type=Path, help="OCR text file for --barcode")
    parser.add_argument("--from-json", type=Path, help="sample_reports.json style list")
    parser.add_argument("--from-seed", action="store_true", help="Use reports already in DB")
    parser.add_argument("--from-sample-data", action="store_true", help="Use data/sample_reports.json")
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--allow-facsimile",
        action="store_true",
        help="Opt-in only: write unscorable OCR-text facsimiles if real scans missing",
    )
    parser.add_argument(
        "--no-tatonetti",
        action="store_true",
        help="Skip Tatonetti zip; try GDC PDF only",
    )
    parser.add_argument("--sync-db", action="store_true", help="Write scan_manifest onto Report rows")
    parser.add_argument("--max-pages", type=int, default=2)
    args = parser.parse_args()

    jobs: list[tuple[str, str]] = []
    if args.barcode:
        text = args.text_file.read_text(encoding="utf-8") if args.text_file else ""
        jobs.append((args.barcode, text))
    if args.from_json:
        items = json.loads(args.from_json.read_text(encoding="utf-8"))
        for item in items:
            jobs.append((item["tcga_barcode"], item.get("report_text") or ""))
    if args.from_sample_data:
        path = REPO_ROOT / "data" / "sample_reports.json"
        items = json.loads(path.read_text(encoding="utf-8"))
        for item in items:
            jobs.append((item["tcga_barcode"], item.get("report_text") or ""))
    if args.from_seed:
        init_db()
        db = SessionLocal()
        try:
            for r in db.query(Report).all():
                jobs.append((r.tcga_barcode, r.report_text))
        finally:
            db.close()

    if not jobs:
        raise SystemExit(
            "No reports selected. Use --from-sample-data, --from-seed, --from-json, or --barcode."
        )

    manifests: dict[str, dict] = {}
    for barcode, text in jobs:
        manifests[barcode] = await cache_one(
            barcode,
            text,
            force=args.force,
            allow_facsimile=args.allow_facsimile,
            prefer_tatonetti=not args.no_tatonetti,
        )

    n_real = sum(1 for m in manifests.values() if is_real_scan_manifest(m))
    print(f"Done: {n_real}/{len(manifests)} cases have real scorable scans.")

    if args.sync_db:
        init_db()
        db = SessionLocal()
        try:
            for row in db.query(Report).all():
                m = load_manifest(row.tcga_barcode)
                if m:
                    row.scan_manifest = m
            db.commit()
            print("Synced scan_manifest onto DB reports.")
        finally:
            db.close()


if __name__ == "__main__":
    asyncio.run(main())
