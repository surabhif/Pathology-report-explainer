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

PathExplain owns the path from **scan page → OCR → structured facts → explanation**:

0. **Scan pages** — Authentic page images only: preferred source is the Tatonetti lab’s Textract-input JPEGs (range-fetched from `imgs_for_aws.zip` into `data/scan_cache/`); alternate source is NCI GDC pathology PDF page renders when GDC is available. OCR-text facsimiles are never shown on the public demo and are never used for CER/WER.
1. **Our OCR** — PathExplain OCR (default **Tesseract**; optional **xAI Grok vision**) runs on authentic cached pages and is tagged with engine + version. TCGA-Reports / Textract (Kefeli et al.) remains the **reference** transcript for CER/WER benchmarks and UI comparison — not claimed as PathExplain OCR.
2. **Structured extraction** — An LLM (or deterministic mock provider) returns JSON facts matching `backend/config/extraction_schema.json`, each with a source quote grounded in the chosen transcript (`text_source=our_ocr|reference`).
3. **Grounded explanation** — A second step writes short sentences **only from extracted facts**, linking each sentence to its sources.
4. **Glossary & reading level** — Medical terms are explained; Flesch–Kincaid grade is reported for the original report and the explanation (target: roughly 6th–8th grade).
5. **Versioning** — Prompts live as editable files under `backend/prompts/`. Every generation and evaluation result is tagged with prompt version and model; OCR runs are tagged with engine/version/timing/cost estimate.

The public demo UI walks users through stages 0–3 as a journey (scan → OCR with Our/Reference/Diff switch → facts/explanation). Public site never accepts arbitrary uploads (PHI).

The API key for any hosted LLM stays on the server. The default provider is **mock** so the demo runs without credentials.

For production-quality extraction/explanation, this project uses **xAI Grok** (`LLM_PROVIDER=xai`) through the OpenAI-compatible endpoint `https://api.x.ai/v1`. The default model id is **`grok-4.20-0309-non-reasoning`** (fast; supports structured / JSON outputs). Set `LLM_MODEL` to pin or change versions (e.g. `grok-4.7`). Configure `LLM_TIMEOUT_SECONDS` for slower models. If `LLM_PROVIDER=xai` is set without a key, the backend falls back to mock. If a hosted response fails validation, heuristic output is labeled as a **fallback** (`provider=mock`, `is_fallback=true`) and excluded from primary evaluation metrics — never silently attributed to Grok.

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
- Demo scan pages are authentic Tatonetti Textract inputs (or GDC PDF renders). Facsimile pages rendered from OCR text are excluded from scoring and from the public stage-1 UI.
- OCR quality depends on the engine: Tesseract is free but can err on dense/noisy pages; Grok vision costs tokens. CER/WER vs Textract is reported only on real scans, with the count of real scans scored shown on the Results dashboard. Latest Tesseract run on 30 authentic Tatonetti pages: CER 0.293 (95% CI 0.180–0.405), WER 0.456 (95% CI 0.332–0.579).
- Public demo does not accept uploads (PHI); admin test upload is explicitly acknowledged and does not store images.

## Disclaimer

PathExplain is an educational and research prototype. It is **not** a medical device, **not** FDA-cleared, and **must not** be used for diagnosis, treatment, or other clinical decisions. Always defer to the original pathology report and the care team.
