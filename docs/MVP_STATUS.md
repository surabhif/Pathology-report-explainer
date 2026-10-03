# MVP status — what works vs stubbed

## Done (end-to-end)

- Public demo: BRCA / COAD / LUAD sample reports → fact sheet, quote highlights, grounded explanation, glossary, Flesch–Kincaid grades, research disclaimer
- No free-text paste box
- Invite-token auth with roles admin / annotator / clinician
- Admin: users/invites, evaluation sets, batches, progress, auto-check job
- Annotator labeling (model output hidden)
- Clinician blinded review (1–5 scores, flags, comments; rubric file-editable)
- Auto-checks: field accuracy vs gold, TCGA metadata agreement, number grounding, unsupported sentences, reading level
- Results dashboard: metrics + 95% CIs, per-field / per-cancer, clinician scores, inter-rater when multi-rated, failures, CSV export
- Version tags on generations (prompt + model/provider)
- Mock LLM provider (default) + OpenAI-compatible provider interface
- Seed data, sample TCGA JSON, download/import script
- Tests (backend 30, frontend smoke), GitHub Actions CI
- Docs: README, DESIGN, DEPLOY, ABOUT/model card

## Thin / stubbed (intentional for days-not-weeks)

- **Live GDC enrichment:** barcode→TSS map + optional API helper; seed uses static metadata blobs. Full live GDC sync is optional (`--fetch-gdc` / network).
- **Alembic:** initial migration present; local MVP uses SQLAlchemy `create_all` on startup.
- **Magic-link email delivery:** invite tokens work; no SMTP/sendgrid — admin copies tokens.
- **Inter-rater:** computed when ≥2 clinicians score the same generation; seed only assigns one clinician (metric appears after dual assignment).
- **Real LLM quality:** mock heuristics power local demos; set `LLM_API_KEY` for hosted models.
- **Vercel serverless FastAPI:** documented as experimental; Railway/Render/Fly recommended for the API.
- **Prompt editor UI:** prompts are versioned files/DB records; editing is file- or admin-DB based, not a rich in-app editor.
- **Full TCGA corpus:** not committed (~35MB CSV); use `download_and_import_tcga.py`.
