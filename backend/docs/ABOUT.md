# About / Model Card — PathExplain

**Research demo — not for clinical use.**

## Problem

Surgical pathology reports encode diagnosis, grade, tumor size, margins, lymph-node status, TNM stage, and biomarkers in dense medical language. Patients and families often cannot interpret them. PathExplain studies whether a constrained AI pipeline can produce **plain-language explanations that stay faithful to the report**, with measurable accuracy and clinician-rated safety.

This is a college-application research project by **Surabhi Fadnavis**, who plans to become a surgical oncologist.

## Data source & citation

Public demo reports come from **TCGA-Reports** only (no free-text paste of real clinical reports in the MVP):

- Source repository: https://github.com/tatonetti-lab/tcga-path-reports (MIT)
- Paper: Kefeli et al., “TCGA-Reports: A Machine-Readable Pathology Report Resource for Benchmarking Text-Based AI Models”, *Patterns* 2024.  
  https://www.cell.com/patterns/fulltext/S2666-3899(24)00024-2
- Underlying reports: open-access **The Cancer Genome Atlas (TCGA)** pathology text
- Cancer types in the MVP demo: breast (BRCA), colon (COAD), lung adenocarcinoma (LUAD) — configurable in `backend/config/cancer_types.json`
- Clinical metadata (when available) is linked via TCGA barcodes / GDC; we never attempt re-identification

A small sample set is committed under `data/sample_reports.json`. The full ~9,500-report corpus is imported via scripts and is not committed.

## Method

1. **Structured extraction** — An LLM (or deterministic mock provider) returns JSON facts matching `backend/config/extraction_schema.json`, each with a source quote.
2. **Grounded explanation** — A second step writes short sentences **only from extracted facts**, linking each sentence to its sources.
3. **Glossary & reading level** — Medical terms are explained; Flesch–Kincaid grade is reported for the original report and the explanation (target: roughly 6th–8th grade).
4. **Versioning** — Prompts live as editable files under `backend/prompts/`. Every generation and evaluation result is tagged with prompt version and model.

The API key for any hosted LLM stays on the server. The default provider is **mock** so the demo runs without credentials.

For production-quality extraction/explanation, this project uses **xAI Grok** (`LLM_PROVIDER=xai`) through the OpenAI-compatible endpoint `https://api.x.ai/v1`. The default model id is **`grok-4.7`**, which supports structured / JSON outputs; set `LLM_MODEL` to pin or change versions. If `LLM_PROVIDER=xai` is set without a key, the backend falls back to mock.

## Evaluation

Built into the product as roles and tasks:

- **Gold labeling (annotators):** highlight spans for fact-sheet fields without seeing model output.
- **Automatic checks:** field accuracy vs gold; agreement with TCGA/GDC metadata when present; every number in the explanation must appear in the report; unsupported-sentence detection; reading level before/after.
- **Clinician review:** blinded side-by-side scoring of accuracy, completeness, and potential to mislead/harm (1–5), plus sentence flags and comments. Rubric is editable (`backend/config/rubric.json`).
- **Dashboard:** per-field and per-cancer metrics with 95% confidence intervals, score summaries, inter-rater agreement when multiple clinicians review the same item, failure examples, CSV export.

## Limitations

- Not validated for clinical care; sample sizes in the MVP seed are small.
- Mock extraction is heuristic and will miss or mis-parse complex reports.
- Real LLMs can still hallucinate; grounding checks reduce but do not eliminate risk.
- Reading-level formulas are approximate.
- TSS→cancer-type mapping for import is a curated subset and may mis-label rare edge cases until enriched via GDC.
- English-only, TCGA-era report style.

## Disclaimer

PathExplain is an educational and research prototype. It is **not** a medical device, **not** FDA-cleared, and **must not** be used for diagnosis, treatment, or other clinical decisions. Always defer to the original pathology report and the care team.
