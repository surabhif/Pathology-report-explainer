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

Salil’s product ask: show how a scanned page becomes structured content.

1. **Scanned report** — open-access TCGA pathology PDF page images from the NCI GDC (`Clinical` / `Pathology Report` / `PDF`), fetched at import/build time into `data/scan_cache/` (never hot-linked at runtime). If GDC is down while packaging, we ship a clearly labeled **OCR-text facsimile** so the layout still demos; the UI must not claim it is a GDC scan.
2. **OCR text** — machine-readable text from **TCGA-Reports (Kefeli et al., Patterns 2024; AWS Textract)**. PathExplain does **not** run OCR. Stage 2 is labeled and cited accordingly.
3. **Facts & explanation** — PathExplain’s contribution: structured fact sheet with quotes + grounded plain-language explanation. Clicking a fact highlights its quote in the OCR text (side-by-side).

Tradeoff: highlighting matching regions on the scan image would need OCR bounding boxes we do not have from Textract outputs in this corpus; we skip scan-region highlight rather than fake it.

## Future work

- **Live OCR on uploaded scans** — optional later path: accept a page image, run OCR (e.g. Textract or open-source), then feed text into the existing extract→explain pipeline. Easy to add as a new stage-1 input without changing stages 2→3. **Not in MVP** (ethics: no PHI paste; keep demo on public TCGA only).
- Prefer real GDC PDF page renders over facsimiles whenever GDC is reachable (`python backend/scripts/fetch_scan_pages.py --from-sample-data --force`).
- Optional: use Textract geometry (if re-run) to highlight quote regions on the scan.

## What we deliberately stubbed or kept thin in MVP

See the PR summary for the current stub list. Examples of intentional thin spots: live GDC enrichment is optional/offline-tolerant; Alembic exists but SQLite `create_all` is the happy path; inter-rater agreement appears when multiple clinicians share an item but needs enough dual reviews to be meaningful; scan-region highlighting is omitted without bounding boxes.

## Editing research knobs

Prompts, schema, glossary, rubric, and cancer types live in files under `backend/prompts/` and `backend/config/` so Surabhi can iterate without hunting through React components.
