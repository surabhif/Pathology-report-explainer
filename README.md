# Pathology Report Explainer (PathExplain)

**Research demo — not for clinical use.**

A college-application research project by **Surabhi Fadnavis** (aspiring surgical oncologist). The app explains de-identified TCGA pathology reports in plain language, with every fact tied to a quote in the source report, and builds evaluation workflows (gold labeling, automatic checks, clinician review) into the product.

## Architecture

```text
┌─────────────────┐         ┌──────────────────────────────┐
│  React (Vite)   │  /api   │  FastAPI backend             │
│  public demo    │────────▶│  owns LLM key                │
│  admin / tasks  │         │  extract → grounded explain  │
│  results        │         │  checks + metrics            │
└─────────────────┘         └───────────┬──────────────────┘
                                        │
                        ┌───────────────┼───────────────┐
                        ▼               ▼               ▼
                   SQLite/Postgres   prompts/        LLM provider
                   (DATABASE_URL)    schema/rubric   (mock | xAI Grok | OpenAI-compatible)
```

- **Frontend:** React + TypeScript (Vite)
- **Backend:** Python FastAPI — LLM API keys never reach the browser
- **Default LLM:** deterministic **mock** provider (no API key required)
- **Hosted LLM (chosen for this project):** **xAI Grok** via `LLM_PROVIDER=xai` → `https://api.x.ai/v1` (OpenAI-compatible); default model `grok-4.7` (structured/JSON output). Model id is always overridable with `LLM_MODEL`.
- **Data:** TCGA-Reports (Kefeli et al., Patterns 2024); small sample committed under `data/`

## Quick start (mock provider)

From the repo root:

```bash
# 1) Backend
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

In a second terminal:

```bash
# 2) Frontend
cd frontend
npm install
npm run dev
```

Open http://localhost:5173

Or use the Makefile:

```bash
make install
make dev          # starts backend + frontend (two processes via script)
```

### Demo accounts (invite tokens)

On the Login page, redeem one of:

| Role | Email | Invite token |
|------|-------|--------------|
| Admin | surabhi@example.com | `DEMO_ADMIN_TOKEN` |
| Annotator | annotator@example.com | `DEMO_ANNOTATOR_TOKEN` |
| Clinician | clinician@example.com | `DEMO_CLINICIAN_TOKEN` |

## End-to-end evaluation loop

1. **Public demo** (`/`): pick Breast / Colon / Lung → open a report → fact sheet, quotes, explanation, glossary, reading levels.
2. **Admin** (`/admin` + `DEMO_ADMIN_TOKEN`): review seeded evaluation set & batches, invite clinicians, run automatic checks.
3. **Annotator** (`/annotate`): label fact-sheet fields by highlighting spans (model output is hidden).
4. **Auto-checks** (Admin → Run automatic checks): field accuracy vs gold, TCGA metadata agreement, number grounding, unsupported sentences, reading levels.
5. **Clinician** (`/review`): side-by-side report + explanation; score accuracy / completeness / harm potential (1–5); flag sentences; comment. Prompt/model version is hidden.
6. **Results** (`/results`): per-field and per-cancer metrics with 95% CIs, clinician score summaries, failure examples, CSV export.

## Environment variables

See [`.env.example`](.env.example). Important ones:

| Variable | Purpose | Local default |
|----------|---------|---------------|
| `DATABASE_URL` | Postgres or SQLite | SQLite file in `backend/` |
| `LLM_PROVIDER` | `mock`, `xai`, or `openai` | `mock` |
| `LLM_MODEL` | Model id | `mock-heuristic-v1` (local); for xAI use `grok-4.7` |
| `LLM_API_KEY` | Server-only key (xAI or OpenAI) | empty |
| `XAI_API_KEY` | Optional alias when `LLM_PROVIDER=xai` | empty |
| `LLM_BASE_URL` | OpenAI-compatible base URL | empty → `https://api.x.ai/v1` for xai |
| `CORS_ORIGINS` | Allowed front-end origins | localhost:5173 |
| `SEED_ON_STARTUP` | Seed demo users/reports | `true` |
| `VITE_API_BASE_URL` | Front-end API origin (prod) | unset (Vite proxy) |

To switch on Grok after you have a console key:

```bash
export LLM_PROVIDER=xai
export LLM_MODEL=grok-4.7
export LLM_API_KEY=xai-...   # or XAI_API_KEY=...
export LLM_BASE_URL=https://api.x.ai/v1
```

If `LLM_PROVIDER=xai` (or `openai`) is set but no key is present, the backend **falls back to mock** so local demos still run.

## Tests

```bash
cd backend && source .venv/bin/activate && pytest -q
cd frontend && npm test -- --run
```

## Importing more TCGA reports

```bash
# Small committed sample
cd backend && source .venv/bin/activate
python scripts/import_tcga.py ../data/sample_reports.json

# Download full zip and import a stratified slice (not committed)
python scripts/download_and_import_tcga.py --cancer-types BRCA,COAD,LUAD --limit-per-type 50
```

Cancer types are configurable in `backend/config/cancer_types.json`.

## Editable research artifacts

| Path | What Surabhi can edit |
|------|------------------------|
| `backend/prompts/` | Extraction & explanation prompts (versioned) |
| `backend/config/extraction_schema.json` | Fact-sheet schema |
| `backend/config/glossary.json` | Medical glossary |
| `backend/config/rubric.json` | Clinician review rubric |
| `backend/config/cancer_types.json` | Enabled cancer types |
| `docs/DESIGN.md` | Design decisions & tradeoffs |

## Docs

- [`docs/DESIGN.md`](docs/DESIGN.md) — why the system is shaped this way
- [`DEPLOY.md`](DEPLOY.md) — Vercel + Postgres + env vars
- [`data/README.md`](data/README.md) — dataset & citation
- [`backend/docs/ABOUT.md`](backend/docs/ABOUT.md) — model card content (About page)

## Citation & credit

- Kefeli et al., “TCGA-Reports: A Machine-Readable Pathology Report Resource for Benchmarking Text-Based AI Models”, *Patterns* 2024. https://www.cell.com/patterns/fulltext/S2666-3899(24)00024-2
- The Cancer Genome Atlas (TCGA) — open-access pathology reports
- Repo source: https://github.com/tatonetti-lab/tcga-path-reports (MIT)

**Disclaimer:** This is a research prototype for education and evaluation. It is not a medical device and must not be used for clinical decisions.
