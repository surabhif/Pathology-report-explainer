#!/usr/bin/env python3
"""Build a stratified OCR benchmark set (≥30) with Textract text + Tatonetti page images.

1) Download TCGA_Reports.csv.zip for machine-readable reference text.
2) Intersect barcodes with cases present in the remote imgs_for_aws.zip (central dir only).
3) Pick N per cancer type (BRCA/COAD/LUAD), write JSON, optionally fetch page images.

Usage (from repo root):
  python backend/scripts/prepare_ocr_benchmark_set.py --per-type 10 --fetch-scans
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import sys
import tempfile
import zipfile
from collections import defaultdict
from pathlib import Path
from urllib.request import urlretrieve

BACKEND_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_ROOT.parent
sys.path.insert(0, str(BACKEND_ROOT))

from app.services.gdc import project_id_for_cancer
from app.services.scan_assets import ensure_scan_pages_for_barcode, is_real_scan_manifest
from app.services.tatonetti_pages import TATONETTI_IMGS_ZIP_URL, parse_member

ZIP_URL = "https://github.com/tatonetti-lab/tcga-path-reports/raw/main/TCGA_Reports.csv.zip"

TSS_TO_CANCER: dict[str, str] = {
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
}


def barcode_from_filename(patient_filename: str) -> str:
    return patient_filename.split(".", 1)[0]


def cancer_from_barcode(barcode: str) -> str | None:
    parts = barcode.split("-")
    if len(parts) < 3:
        return None
    return TSS_TO_CANCER.get(parts[1])


def download_csv(dest: Path) -> Path:
    zip_path = dest / "TCGA_Reports.csv.zip"
    print(f"Downloading {ZIP_URL} …")
    urlretrieve(ZIP_URL, zip_path)
    with zipfile.ZipFile(zip_path) as zf:
        zf.extract("TCGA_Reports.csv", path=dest)
    return dest / "TCGA_Reports.csv"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--per-type", type=int, default=10)
    parser.add_argument("--out", type=Path, default=REPO_ROOT / "data" / "ocr_benchmark_set.json")
    parser.add_argument("--fetch-scans", action="store_true")
    parser.add_argument("--max-pages", type=int, default=2)
    args = parser.parse_args()

    demo_path = REPO_ROOT / "data" / "sample_reports.json"
    demo_items = json.loads(demo_path.read_text(encoding="utf-8"))

    tmp = Path(tempfile.mkdtemp(prefix="tcga_ocr_bench_"))
    csv_path = download_csv(tmp)

    by_type: dict[str, list[dict]] = defaultdict(list)
    with csv_path.open(newline="", encoding="utf-8", errors="replace") as f:
        for row in csv.DictReader(f):
            fn = row.get("patient_filename") or ""
            text = (row.get("text") or "").strip()
            if not fn or len(text) < 400:
                continue
            barcode = barcode_from_filename(fn)
            ctype = cancer_from_barcode(barcode)
            if ctype not in {"BRCA", "COAD", "LUAD"}:
                continue
            case = "-".join(barcode.split("-")[:3])
            by_type[ctype].append(
                {
                    "tcga_barcode": case,
                    "cancer_type": ctype,
                    "project_id": project_id_for_cancer(ctype),
                    "report_text": text[:12000],
                    "source": "tcga",
                    "gdc_metadata": {"patient_filename": fn, "from_ocr_benchmark_prep": True},
                }
            )

    print("Listing Tatonetti zip central directory (range request)…")
    from remotezip import RemoteZip

    present: set[str] = set()
    with RemoteZip(TATONETTI_IMGS_ZIP_URL) as zf:
        for name in zf.namelist():
            parsed = parse_member(name)
            if parsed:
                present.add(parsed[0])
    print(f"Cases with page images in zip: {len(present)}")

    selected: list[dict] = []
    for d in demo_items:
        if d["tcga_barcode"] in present:
            selected.append(
                {
                    "tcga_barcode": d["tcga_barcode"],
                    "cancer_type": d["cancer_type"],
                    "project_id": d.get("project_id") or project_id_for_cancer(d["cancer_type"]),
                    "report_text": d["report_text"],
                    "source": "tcga",
                    "gdc_metadata": {**(d.get("gdc_metadata") or {}), "demo_sample": True},
                }
            )

    counts: dict[str, int] = defaultdict(int)
    for item in selected:
        counts[item["cancer_type"]] += 1

    for ctype in ("BRCA", "COAD", "LUAD"):
        seen = {s["tcga_barcode"] for s in selected}
        for item in by_type[ctype]:
            if counts[ctype] >= args.per_type:
                break
            if item["tcga_barcode"] in seen:
                continue
            if item["tcga_barcode"] not in present:
                continue
            selected.append(item)
            seen.add(item["tcga_barcode"])
            counts[ctype] += 1

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(selected, indent=2), encoding="utf-8")
    print(f"Wrote {len(selected)} reports to {args.out}: {dict(counts)}")

    if args.fetch_scans:

        async def _fetch() -> None:
            n_real = 0
            for item in selected:
                m = await ensure_scan_pages_for_barcode(
                    item["tcga_barcode"],
                    item["report_text"],
                    allow_facsimile=False,
                    prefer_tatonetti=True,
                    max_pages=args.max_pages,
                    force=True,
                )
                ok = is_real_scan_manifest(m)
                n_real += int(ok)
                print(
                    f"  {item['tcga_barcode']}: source={m.get('source')} "
                    f"pages={len(m.get('pages') or [])} real={ok}"
                )
            print(f"Cached real scans for {n_real}/{len(selected)} cases.")

        asyncio.run(_fetch())


if __name__ == "__main__":
    main()
