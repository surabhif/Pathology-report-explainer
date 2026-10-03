# Sample data

This folder holds a **small committed sample** of de-identified TCGA pathology reports for local demo and CI.

| File | Purpose |
|------|---------|
| `sample_reports.json` | Six real TCGA-Reports excerpts (2 BRCA, 2 COAD, 2 LUAD) |

## Full dataset (not committed)

The full corpus is ~9,500 reports from [TCGA-Reports](https://github.com/tatonetti-lab/tcga-path-reports) (`TCGA_Reports.csv.zip`, MIT license).

```bash
# From repo root, with backend deps installed:
python backend/scripts/download_and_import_tcga.py \
  --cancer-types BRCA,COAD,LUAD \
  --limit-per-type 50
```

Never attempt to re-identify patients. Reports are open-access TCGA data; cite Kefeli et al., Patterns 2024, and credit TCGA.

## Citation

Kefeli J, et al. TCGA-Reports: A Machine-Readable Pathology Report Resource for Benchmarking Text-Based AI Models. *Patterns*. 2024.
https://www.cell.com/patterns/fulltext/S2666-3899(24)00024-2
