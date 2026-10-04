# Pathology Report Explainer — Backend

FastAPI MVP with SQLite (Postgres-ready), invite-token auth, mock / **xAI Grok** /
OpenAI LLM providers, grounded explanations, and automatic evaluation checks.

## Quick start

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Demo tokens: `DEMO_ADMIN_TOKEN`, `DEMO_ANNOTATOR_TOKEN`, `DEMO_CLINICIAN_TOKEN`.

OpenAPI docs: http://127.0.0.1:8000/docs

## Tests

```bash
cd backend
pip install -r requirements.txt
python -m pytest tests/ -q
```

## Environment

See `.env.example`. Key vars: `DATABASE_URL`, `LLM_PROVIDER`, `LLM_MODEL`,
`LLM_API_KEY`, `LLM_BASE_URL`.
