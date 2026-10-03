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

A deterministic heuristic/mock provider ships so the app, tests, and demos run **without an API key**. Hosted models share one OpenAI-compatible client. For this project Salil chose **xAI Grok** (`LLM_PROVIDER=xai`, base URL `https://api.x.ai/v1`, default model `grok-4.7` with structured/JSON output). OpenAI remains available via `LLM_PROVIDER=openai`. Surabhi can swap models with `LLM_MODEL` and compare versions because every generation stores prompt + model tags.

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

## What we deliberately stubbed or kept thin in MVP

See the PR summary for the current stub list. Examples of intentional thin spots: live GDC enrichment is optional/offline-tolerant; Alembic exists but SQLite `create_all` is the happy path; inter-rater agreement appears when multiple clinicians share an item but needs enough dual reviews to be meaningful.

## Editing research knobs

Prompts, schema, glossary, rubric, and cancer types live in files under `backend/prompts/` and `backend/config/` so Surabhi can iterate without hunting through React components.
