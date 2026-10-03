# Deploy guide (PathExplain)

Public demo (no secrets):

| Piece | Host |
|-------|------|
| Front end | [Vercel](https://pathology-report-explainer.vercel.app) |
| API | [Render](https://pathology-report-explainer-api.onrender.com) |
| Database | Neon Postgres |

You do **not** need deploy credentials to develop locally. This document is the checklist for the live stack above.

## Recommended shape

| Piece | Where |
|-------|--------|
| React front end | **Vercel** — project root directory `frontend/` |
| FastAPI back end | **Render** Web Service — root directory `backend/` |
| Database | **Neon** Postgres (`DATABASE_URL`) |
| LLM | **xAI Grok** via OpenAI-compatible `https://api.x.ai/v1` (`LLM_API_KEY` on Render only) |

## Neon (Postgres)

1. Create a Neon project and copy the connection string.
2. Use the SQLAlchemy form with the psycopg v3 driver (required; see `requirements.txt`):

   `postgresql+psycopg://USER:PASSWORD@HOST/DBNAME?sslmode=require`

3. Set that value as `DATABASE_URL` on Render. Do not commit the real DSN.
4. The API uses SQLAlchemy `pool_pre_ping=True` so Neon’s ~5-minute idle disconnect does not break the next request.

## Render (API)

### Service settings

| Setting | Value |
|---------|--------|
| Root Directory | `backend` |
| Runtime | Python |
| **`PYTHON_VERSION`** | **`3.12.3`** (Render env var / runtime pin) |
| Build Command | `pip install -r requirements.txt` |
| Start Command | `uvicorn app.main:app --host 0.0.0.0 --port $PORT` |
| Auto-Deploy | **Off** (manual deploy from the merged/main commit you trust) |

Health check path: `/api/health` → `{"ok": true, "provider": …}`.

### Backend environment variables (Render)

| Name | Required | Notes |
|------|----------|-------|
| `DATABASE_URL` | Yes | Neon `postgresql+psycopg://…?sslmode=require` |
| `APP_ENV` | Yes (prod) | Set to `production` so known `DEMO_*` defaults are **never** seeded |
| `CORS_ORIGINS` | Yes | `https://pathology-report-explainer.vercel.app` |
| `TRUST_PROXY_HEADERS` | Yes (prod) | `true` on Render so rate limits use `X-Forwarded-For` |
| `LLM_PROVIDER` | Yes | `xai` (or `mock` without a key) |
| `LLM_MODEL` | Recommended | Default if unset for xAI: **`grok-4.20-0309-non-reasoning`** (fast). Override e.g. `grok-4.7` if you accept longer latency |
| `LLM_API_KEY` | For xAI | From [console.x.ai](https://console.x.ai) — **never** in `VITE_*` |
| `XAI_API_KEY` | Optional | Alias when `LLM_PROVIDER=xai` |
| `LLM_BASE_URL` | Optional | `https://api.x.ai/v1` |
| `LLM_TIMEOUT_SECONDS` | Optional | Default `120`. Raise if you use a slow reasoning model |
| `SEED_ON_STARTUP` | Optional | `true` to seed sample reports/prompts; demo **users** only if `DEMO_*_TOKEN` set |
| `DEMO_ADMIN_TOKEN` | Optional | If unset in production, demo admin is **not** seeded |
| `DEMO_ANNOTATOR_TOKEN` | Optional | Same |
| `DEMO_CLINICIAN_TOKEN` | Optional | Same |
| `RATE_LIMIT_EXPLAIN` | Optional | e.g. `30/minute` |

Invite clinicians from the Admin UI when demo tokens are not used.

## Vercel (front end)

1. Import this GitHub repo.
2. **Root Directory:** `frontend`
3. Build: `npm run build` · Output: `dist`
4. Env: `VITE_API_BASE_URL=https://pathology-report-explainer-api.onrender.com` (no trailing slash)
5. Redeploy after changing `VITE_*` (inlined at build time).
6. SPA routing: `frontend/vercel.json` rewrites non-asset paths to `/index.html` so `/login` and `/admin` work on refresh.

## Local development

```bash
cd backend && python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

cd frontend && npm install && npm run dev
```

With `APP_ENV=development` (default) and no `DEMO_*_TOKEN` overrides, local seed uses convenience tokens `DEMO_ADMIN_TOKEN` / `DEMO_ANNOTATOR_TOKEN` / `DEMO_CLINICIAN_TOKEN`.

## LLM notes (xAI)

- Preferred default model for this app: **`grok-4.20-0309-non-reasoning`** (~few seconds, structured JSON).
- `grok-4.7` can take well over a minute with large reasoning traces; if you use it, raise `LLM_TIMEOUT_SECONDS` (e.g. 180+).
- Timeouts and network errors return **502/504** with a clear `detail.message` for the UI — not a bare 500.
- If the hosted model returns invalid JSON/schema, the app may use heuristic output but labels it as **`provider=mock`**, `is_fallback=true`, and excludes those rows from primary evaluation metrics.

## Security checklist

- [ ] No secrets in git  
- [ ] `LLM_API_KEY` only on Render  
- [ ] `APP_ENV=production` and no known default demo tokens unless you set unique `DEMO_*_TOKEN` values  
- [ ] `CORS_ORIGINS` limited to the Vercel origin  
- [ ] `TRUST_PROXY_HEADERS=true` only behind Render (or another trusted proxy)  
- [ ] Banner remains: research demo, not for clinical use  
