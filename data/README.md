# Sample data

This folder holds a **small committed sample** of de-identified TCGA pathology reports for local demo and CI.

| Path | Purpose |
|------|---------|
| `sample_reports.json` | Stratified TCGA-Reports excerpts for the public demo + OCR benchmark (10 BRCA / 10 COAD / 10 LUAD) |
| `ocr_benchmark_set.json` | Same stratified set used to build/refetch the OCR benchmark |
| `scan_cache/<case>/` | Cached **authentic** page images + `manifest.json` (Tatonetti Textract inputs preferred; GDC PDF renders as alternate). Facsimiles are never the default and are unscorable. |

## Full dataset (not committed)

The full corpus is ~9,500 reports from [TCGA-Reports](https://github.com/tatonetti-lab/tcga-path-reports) (`TCGA_Reports.csv.zip`, MIT license).

```bash
# From repo root, with backend deps installed:
python backend/scripts/download_and_import_tcga.py \
  --cancer-types BRCA,COAD,LUAD \
  --limit-per-type 50

# Rebuild the stratified OCR benchmark set and range-fetch Tatonetti pages only:
python backend/scripts/prepare_ocr_benchmark_set.py --per-type 10 --fetch-scans

# Refresh authentic scan pages (Tatonetti first, then GDC). Facsimiles opt-in only:
python backend/scripts/fetch_scan_pages.py --from-sample-data --force --sync-db
# python backend/scripts/fetch_scan_pages.py --from-sample-data --force --allow-facsimile  # unscorable
```

**Authentic scan sources (cited in each `manifest.json`):**

1. **Tatonetti Textract inputs** (preferred for OCR benchmarks) — page JPEGs from `https://tatonettilab-resources.s3.us-west-1.amazonaws.com/tcga-path-reports/imgs_for_aws.zip` (24 GB; we HTTP range-request only the members for our barcodes via `remotezip`).
2. **NCI GDC pathology PDFs** (alternate when GDC is up) — `data_category=Clinical`, `data_type=Pathology Report`, `data_format=PDF`.

OCR-text facsimiles are circular vs the Textract reference and must not be scored or shown as scans. Never hot-link remote scan URLs at runtime.

Never attempt to re-identify patients. Reports are open-access TCGA data; cite Kefeli et al., Patterns 2024, and credit TCGA.

## Citation

Kefeli J, et al. TCGA-Reports: A Machine-Readable Pathology Report Resource for Benchmarking Text-Based AI Models. *Patterns*. 2024.
https://www.cell.com/patterns/fulltext/S2666-3899(24)00024-2
