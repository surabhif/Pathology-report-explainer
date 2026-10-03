# Sample data

This folder holds a **small committed sample** of de-identified TCGA pathology reports for local demo and CI.

| Path | Purpose |
|------|---------|
| `sample_reports.json` | Six real TCGA-Reports excerpts (2 BRCA, 2 COAD, 2 LUAD) |
| `scan_cache/<case>/` | Cached page images + `manifest.json` for the public demo journey (GDC PDF renders when available; otherwise honestly labeled OCR-text facsimiles) |

## Full dataset (not committed)

The full corpus is ~9,500 reports from [TCGA-Reports](https://github.com/tatonetti-lab/tcga-path-reports) (`TCGA_Reports.csv.zip`, MIT license).

```bash
# From repo root, with backend deps installed:
python backend/scripts/download_and_import_tcga.py \
  --cancer-types BRCA,COAD,LUAD \
  --limit-per-type 50

# Also cache scan pages for any imported report:
python backend/scripts/download_and_import_tcga.py \
  --cancer-types BRCA,COAD,LUAD \
  --limit-per-type 10 \
  --fetch-scans

# Refresh only the demo sample scan cache:
python backend/scripts/fetch_scan_pages.py --from-sample-data --force --sync-db
```

Original scans are open-access TCGA pathology report PDFs on the NCI GDC (`data_category=Clinical`, `data_type=Pathology Report`, `data_format=PDF`). The Tatonetti lab also hosts Textract input page images; for MVP we prefer GDC PDFs (smaller) and fall back to labeled OCR facsimiles if GDC is unreachable. Never hot-link remote scan URLs at runtime.

Never attempt to re-identify patients. Reports are open-access TCGA data; cite Kefeli et al., Patterns 2024, and credit TCGA.

## Citation

Kefeli J, et al. TCGA-Reports: A Machine-Readable Pathology Report Resource for Benchmarking Text-Based AI Models. *Patterns*. 2024.
https://www.cell.com/patterns/fulltext/S2666-3899(24)00024-2
