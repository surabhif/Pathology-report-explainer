# MVP status — what works vs stubbed

## Done (end-to-end)

- Public demo: BRCA / COAD / LUAD → **three-stage journey** (cached scan → **Our OCR** vs Textract reference + diff → fact sheet + grounded explanation)
- PathExplain OCR: configurable `OCR_ENGINE` (**tesseract** default, **xai_vision** optional), engine/version tags, timing, cost estimate, disk+DB cache
- OCR benchmark vs TCGA-Reports (CER/WER) + extraction-impact; Results dashboard section
- No free-text paste box; admin-only de-identified upload test (no image retention)
- Invite-token auth with roles admin / annotator / clinician
- Admin: users/invites, evaluation sets, batches, progress, auto-check job, OCR benchmark
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
- `backend/Dockerfile` for Render free-tier Tesseract

## Thin / stubbed (intentional for days-not-weeks)

- **Live GDC enrichment:** barcode→TSS map + optional API helper; seed uses static metadata blobs. Full live GDC sync is optional (`--fetch-gdc` / network).
- **GDC scan PDFs at cache time:** when GDC is unreachable, demo ships labeled OCR-text facsimiles; re-run `fetch_scan_pages.py --force` when GDC is up.
- **Scan-region highlight:** omitted without Textract bounding boxes; OCR-text quote highlight is implemented.
- **Native Render without Docker:** Tesseract unavailable — use Docker runtime or `OCR_ENGINE=xai_vision`/`mock`.
- **Alembic:** initial migration present; local MVP uses SQLAlchemy `create_all` on startup.
- **Magic-link email delivery:** invite tokens work; no SMTP/sendgrid — admin copies tokens.
- **Inter-rater:** computed when ≥2 clinicians score the same generation; seed only assigns one clinician (metric appears after dual assignment).
- **Real LLM quality:** mock heuristics power local demos; set `LLM_PROVIDER=xai` and `LLM_API_KEY` (or `XAI_API_KEY`) for Grok. Falls back to mock if the key is missing.
- **Vercel serverless FastAPI:** documented as experimental; Railway/Render/Fly recommended for the API.
- **Prompt editor UI:** prompts are versioned files/DB records; editing is file- or admin-DB based, not a rich in-app editor.
- **Full TCGA corpus:** not committed (~35MB CSV); use `download_and_import_tcga.py`.
