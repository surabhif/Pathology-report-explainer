# Design decisions (PathExplain MVP)

Plain-language notes so Surabhi can explain every choice in interviews.

## Problem

Pathology reports are written for clinicians. Patients and families often cannot understand diagnosis, stage, margins, nodes, or biomarkers. The research question: can a carefully constrained LLM pipeline turn a de-identified report into a **grounded**, grade-level explanation that clinicians judge as accurate and low-risk to mislead?

## Why TCGA-Reports only (no paste box)

- **Ethics & safety:** Free-text paste invites real patient reports into a research demo. The MVP avoids that entirely.
- **Reproducibility:** A public corpus (Kefeli et al., 2024) lets others re-run the same cases.
- **Evaluation:** Shared barcodes connect to GDC clinical metadata for agreement checks.

Tradeoff: less “wow” for casual visitors; better integrity for a college research project.

## Two-step LLM pipeline

1. **Extract** structured JSON facts (diagnosis, grade, size, margins, nodes, TNM, biomarkers) each with a **source quote** and character offsets when possible.
2. **Explain** in plain language **only from those facts**, with each sentence linked to fact keys / quotes.

Why not one-shot summarization? Summaries invent details. Separating extraction from explanation makes grounding checks possible (numbers in explanation ⊆ report; unsupported sentences).

## Mock provider first

A deterministic heuristic/mock provider ships so the app, tests, and demos run **without an API key**. Hosted models share one OpenAI-compatible client. For this project Salil chose **xAI Grok** (`LLM_PROVIDER=xai`, base URL `https://api.x.ai/v1`, default model `grok-4.20-0309-non-reasoning` for low-latency structured/JSON). OpenAI remains available via `LLM_PROVIDER=openai`. Surabhi can swap models with `LLM_MODEL` and compare versions because every generation stores prompt + model tags. Heuristic fallbacks after validation failure are labeled `is_fallback` and stored as `provider=mock`.

Tradeoff: mock quality is weaker than Grok; that’s acceptable for wiring the evaluation science before the API key is added.

## Evaluation is a first-class product surface

Salil’s hard requirement: evaluation as workflows, not a spreadsheet afterthought.

| Role | Job |
|------|-----|
| Admin | Import, sets, batches, invites, auto-check jobs, progress |
| Annotator | Gold spans **without** seeing model output (reduces anchoring bias) |
| Clinician | Blinded review (no prompt/model shown); editable rubric |

Automatic checks cover field accuracy, TCGA metadata agreement, number grounding, unsupported sentences, and reading level (Flesch–Kincaid; target ~6–8).

## Metrics with confidence intervals

Point estimates alone overstate certainty on small N. The dashboard uses binomial proportion CIs (Wilson / normal approximation) per field and cancer type so early results stay honest.

## Auth: invite tokens

Clinicians should not fight OAuth SSO for a pilot. Invite / magic-style tokens redeem into short-lived sessions. Demo tokens are seeded for local use.

Tradeoff: weaker than full IdP; fine for a closed research pilot.

## Persistence

SQLAlchemy models work on **SQLite locally** and **Postgres in production** (`DATABASE_URL`). Seed-on-startup keeps `make dev` one step for reviewers.

## Front-end choices

React (required) + Vite + TypeScript. Simple CSS with a calm teal/slate research look — not a generic “AI purple” template. Brand **PathExplain** is hero-level on the landing page.

## Three-stage public demo journey

Salil’s product ask: show how a scanned page becomes structured content — **owned end-to-end by PathExplain**.

1. **Scanned report** — open-access TCGA pathology PDF page images from the NCI GDC (`Clinical` / `Pathology Report` / `PDF`), fetched at import/build time into `data/scan_cache/` (never hot-linked at runtime). If GDC is down while packaging, we ship a clearly labeled **OCR-text facsimile** so the layout still demos; the UI must not claim it is a GDC scan.
2. **OCR text** — PathExplain runs **its own OCR** on the cached pages. Default engine: **Tesseract** (free, Render-friendly via `backend/Dockerfile`). Optional: **xAI Grok vision** (`OCR_ENGINE=xai_vision`) through chat completions image input (`image_url` / `detail=low|high`). Stage 2 also keeps the **TCGA-Reports / Textract** transcript (Kefeli et al.) as a **reference** for CER/WER and side-by-side / diff comparison — not as “our” OCR.
3. **Facts & explanation** — structured fact sheet + grounded explanation. Users can explain from Our OCR or the reference transcript; quotes ground in the chosen text.

### OCR engine comparison (why Tesseract is default)

| Engine | Pros | Cons | When to use |
|--------|------|------|-------------|
| **Tesseract** (default) | Free; no API key; predictable; fits Render free tier with Dockerfile | Weaker on noisy scans | Demo, CI, benchmarks, cost control |
| **xAI Grok vision** | Strong on hard layouts; uses existing `LLM_PROVIDER=xai` key | Token + latency cost; needs key | Ablations / quality comparison (`OCR_ENGINE=xai_vision`) |

Every OCR run stores `engine`, `engine_version`, timing (`duration_ms`), and optional `estimated_cost_usd`. Results are disk-cached under `data/ocr_cache/` and in `ocr_runs` so demos do not re-spend vision tokens.

**Cost / latency bounds:** max `OCR_MAX_PAGES` (default 2); vision `OCR_VISION_DETAIL=low` by default. Rough Grok vision budget: ~$0.002/page at low detail (order-of-magnitude; image tokens dominate). Tesseract: $0, typically &lt;2s/page locally.

**PHI:** public demo never accepts arbitrary uploads. Admin-only `POST /api/admin/ocr/upload-test` requires `acknowledge_deidentified=true`, accepts page images only, and does **not** store image bytes.

### Benchmark

Admin → Run OCR benchmark (or `POST /api/admin/ocr/benchmark`) runs stratified sample reports (by cancer type), measures CER/WER vs Textract reference, and when gold labels exist compares field-extraction accuracy from Our OCR vs reference text. Results appear on the Results dashboard (`ocr_benchmark`).

## Future work

- Prefer real GDC PDF page renders over facsimiles whenever GDC is reachable (`python backend/scripts/fetch_scan_pages.py --from-sample-data --force`).
- Optional: Textract geometry for scan-region quote highlight.
- Optional: PaddleOCR / EasyOCR as a third engine for ablations.
- Broader OCR benchmark beyond the six seeded samples once more scan pages are cached.

## What we deliberately stubbed or kept thin in MVP

See the PR summary for the current stub list. Examples of intentional thin spots: live GDC enrichment is optional/offline-tolerant; Alembic exists but SQLite `create_all` is the happy path; inter-rater agreement appears when multiple clinicians share an item but needs enough dual reviews to be meaningful; scan-region highlighting is omitted without bounding boxes.

## Editing research knobs

Prompts, schema, glossary, rubric, and cancer types live in files under `backend/prompts/` and `backend/config/` so Surabhi can iterate without hunting through React components.
