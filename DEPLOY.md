# Deploy guide (PathExplain)

You do **not** need deploy credentials to develop. This document is the checklist for when you are ready to host.

## Recommended shape

| Piece | Where |
|-------|--------|
| React front end | **Vercel** (this repo’s `frontend/`) |
| FastAPI back end | **Vercel Python serverless** *or* a small always-on host (Railway / Render / Fly) |
| Database | **Neon** or **Supabase** Postgres (`DATABASE_URL`) |
| LLM | **xAI Grok** (OpenAI-compatible at `https://api.x.ai/v1`) via `LLM_API_KEY` / `XAI_API_KEY` on the **server only** |


### Why the backend may leave Vercel

FastAPI + SQLAlchemy + longer LLM calls fit poorly on short serverless timeouts. For the research pilot, a small Railway/Render/Fly service is often simpler. The repo still includes `frontend/vercel.json` and `api/` notes for a Vercel-centric option.

## Environment variables to set

### Backend

| Name | Required | Notes |
|------|----------|-------|
| `DATABASE_URL` | Yes (prod) | Postgres DSN, e.g. Neon `postgresql+psycopg://…?sslmode=require` |
| `LLM_PROVIDER` | Yes | `mock` until you add a key; then **`xai`** (or `openai`) |
| `LLM_MODEL` | Yes for hosted | **`grok-4.7`** for xAI (structured/JSON capable; override anytime) |
| `LLM_API_KEY` | For real LLM | xAI key from [console.x.ai](https://console.x.ai) — **Never** put in `VITE_*` |
| `XAI_API_KEY` | Optional | Alias accepted when `LLM_PROVIDER=xai` |
| `LLM_BASE_URL` | Optional | For xAI: `https://api.x.ai/v1` (applied automatically if omitted / OpenAI leftover) |
| `CORS_ORIGINS` | Yes | Your Vercel URL, e.g. `https://pathexplain.vercel.app` |
| `SEED_ON_STARTUP` | Optional | `true` once to seed demo users; then `false` |
| `RATE_LIMIT_EXPLAIN` | Optional | e.g. `30/minute` |

### Frontend (Vercel)

| Name | Required | Notes |
|------|----------|-------|
| `VITE_API_BASE_URL` | Yes (if API is separate origin) | e.g. `https://pathexplain-api.up.railway.app` |

## Step-by-step

### 1. Create Postgres

1. Create a Neon or Supabase project.
2. Copy the connection string into `DATABASE_URL`.
3. Prefer the SQLAlchemy URL form: `postgresql+psycopg://…`

### 2. Deploy the API

**Option A — Railway / Render / Fly**

1. Root or `backend/` as the service directory.
2. Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT` (set `working directory` to `backend`).
3. Set the backend env vars above.
4. Hit `GET /api/health` — expect `{"ok": true, …}`.

**Option B — Vercel serverless (experimental)**

1. Use the root `vercel.json` that builds the frontend and exposes Python under `/api`.
2. Expect cold starts and timeout limits; keep `LLM_PROVIDER=mock` until you confirm timeouts.

### 3. Deploy the frontend on Vercel

1. Import this GitHub repo in Vercel.
2. Root directory: `frontend`
3. Build: `npm run build` · Output: `dist`
4. Set `VITE_API_BASE_URL` to the public API origin (no trailing slash).
5. Redeploy after env changes (Vite inlines env at build time).

### 4. Seed & first login

1. With `SEED_ON_STARTUP=true`, restart the API once.
2. Open the site → Login → redeem `DEMO_ADMIN_TOKEN` (change/disable demo tokens before any public launch).
3. Invite real clinicians from Admin (generates invite tokens).

### 5. Flip on xAI Grok

1. Create an API key at [console.x.ai](https://console.x.ai).
2. Set on the **API service only**:
   - `LLM_PROVIDER=xai`
   - `LLM_MODEL=grok-4.7` (or another current Grok text model; must support structured/JSON output)
   - `LLM_API_KEY=…` (or `XAI_API_KEY=…`)
   - `LLM_BASE_URL=https://api.x.ai/v1`
3. Restart the API. Generations are tagged with `provider=xai` and the model id for version comparison.
4. If the key is missing, the app falls back to the mock provider so the site still boots.

(OpenAI remains available via `LLM_PROVIDER=openai` if needed.)

## Accounts needed

1. **GitHub** — this repo  
2. **Vercel** — frontend (and optionally API)  
3. **Neon or Supabase** — Postgres  
4. **LLM provider** — **xAI** API key (preferred); OpenAI also works via the same interface  
5. Optional: **Railway/Render/Fly** — if API is not on Vercel  

## Security checklist

- [ ] No secrets in git  
- [ ] `LLM_API_KEY` only on server  
- [ ] Rotate / remove `DEMO_*` tokens before wide sharing  
- [ ] CORS limited to your front-end origin  
- [ ] Banner remains: research demo, not for clinical use  
- [ ] Do not add a free-text paste box for real reports without IRB/ethics review  
