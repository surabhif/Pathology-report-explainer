# MVP status — what works vs stubbed

## Done (end-to-end)

- Public demo: BRCA / COAD / LUAD → **three-stage journey** (authentic cached scan → **Our OCR** vs Textract reference + diff → fact sheet + grounded explanation); stage 1 hidden when no real scan
- **Stages 1–2 load without LLM calls**; stage 3 runs only on **Generate explanation** (or when a cached generation already exists for the text source)
- Scan images use `apiUrl()` so Vercel frontends load `/api/...` pages from the Render API origin (`VITE_API_BASE_URL`)
- PathExplain OCR: configurable `OCR_ENGINE` (**tesseract** default, **xai_vision** optional), engine/version tags, timing, cost estimate, disk+DB cache; refuses facsimile pages
- **Public Stage 2 = precomputed OCR only** (committed under `data/ocr_cache/` for 30 real scans + stored CER/WER). Live admin runs never replace the public transcript. UI labels precomputed (date/engine) vs live. Default `OCR_MAX_PAGES=1`
- CER/WER via **rapidfuzz** Levenshtein, computed off the event loop (`asyncio.to_thread`) so `/api/health` stays up on Render free; cached metrics reused from disk/`ocr_runs`
- OCR benchmark vs TCGA-Reports on **real scans only** (CER/WER + CIs + extraction-impact); facsimiles excluded; Results shows `n_real_scans_scored`
  - Latest Tesseract (`tesseract-5.3.4`) on 30 Tatonetti pages: **CER 0.293** [0.180, 0.405], **WER 0.456** [0.332, 0.579] (`data/ocr_benchmark_latest.json`)
  - Seed + admin `POST /api/admin/ocr/import-benchmark` load that file into `ocr_benchmark_runs` (idempotent); extraction-impact noted when absent
- Exact-quote grounding normalizes lowercase / whitespace / punctuation and **splits ellipsis-stitched quotes** (`pT3 ... N0`) so each piece must match — not fuzzy semantic matching
- Readability pass: if explanation grade is not below the source and ≤ ~8th grade, **one simplify retry**; outcome recorded in generation checks
- No free-text paste box; admin-only de-identified upload test (no image retention)
- Invite-token auth with roles admin / annotator / clinician; login token is `type=password`; demo-token helper hidden when `APP_ENV=production` (`/api/health.show_demo_tokens`)
- Admin: users/invites, evaluation sets, batches, progress, auto-check job, OCR benchmark import + live run
- Annotator labeling (model output hidden)
- Clinician blinded review (1–5 scores, flags, comments; rubric file-editable)
- Auto-checks: field accuracy vs gold, TCGA metadata agreement, number grounding, unsupported sentences, reading level
- Results dashboard: metrics + 95% CIs, per-field / per-cancer, OCR benchmark, clinician scores, inter-rater when multi-rated, failures, CSV export
- Version tags on generations (prompt + model/provider)
- Mock LLM provider (default) + **xAI Grok** (`LLM_PROVIDER=xai` → `https://api.x.ai/v1`, default `grok-4.20-0309-non-reasoning`) + OpenAI-compatible interface
- Honest fallback labeling (`is_fallback`); primary eval metrics exclude fallbacks
- Scan page cache (`data/scan_cache/`) + `fetch_scan_pages.py` / `--fetch-scans` import
- Seed data, sample TCGA JSON, download/import script
- Tests (backend + frontend), GitHub Actions CI
- Docs: README, DESIGN, DEPLOY (Docker + Tesseract), ABOUT/model card
- `backend/Dockerfile` for Render free-tier Tesseract (build from **repo root** so `data/` is bundled; `OCR_MAX_CONCURRENT=1`, `OCR_MAX_PAGES=1` for 512 MB / 0.15 CPU)
- CI job builds the Docker image and asserts `sample_reports.json` (≥30) + `scan_cache` are present

## Thin / stubbed (intentional for days-not-weeks)

- **Live GDC enrichment:** barcode→TSS map + optional API helper; seed uses static metadata blobs. Full live GDC sync is optional (`--fetch-gdc` / network).
- **Scan source:** demo pages are Tatonetti Textract-input images (range-fetched); GDC PDF remains an alternate when GDC is up. Facsimiles are unscorable and not shown publicly.
- **Scan-region highlight:** omitted without Textract bounding boxes; OCR-text quote highlight is implemented.
- **Native Render without Docker:** Tesseract unavailable — switch the Render service to **Docker** with empty Root Directory + Dockerfile Path `./backend/Dockerfile` (see `DEPLOY.md`), or set `OCR_ENGINE=xai_vision`/`mock`.
- **Render free CPU/memory:** keep `OCR_MAX_CONCURRENT=1` and `OCR_MAX_PAGES=1`; visitors use precomputed OCR. Live admin OCR is ~2.5–3 min/page; overflow returns HTTP 429.
- **Alembic:** initial migration present; local MVP uses SQLAlchemy `create_all` on startup.
- **Magic-link email delivery:** invite tokens work; no SMTP/sendgrid — admin copies tokens.
- **Inter-rater:** computed when ≥2 clinicians score the same generation; seed only assigns one clinician (metric appears after dual assignment).
- **Real LLM quality:** mock heuristics power local demos; set `LLM_PROVIDER=xai` and `LLM_API_KEY` (or `XAI_API_KEY`) for Grok. Falls back to mock if the key is missing.
- **Vercel serverless FastAPI:** documented as experimental; Railway/Render/Fly recommended for the API.
- **Prompt editor UI:** prompts are versioned files/DB records; editing is file- or admin-DB based, not a rich in-app editor.
- **Full TCGA corpus:** not committed (~35MB CSV); use `download_and_import_tcga.py`.
