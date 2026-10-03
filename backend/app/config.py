"""Application settings loaded from environment / .env via pydantic-settings."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/ root — used to resolve relative paths for prompts, config, SQLite
BACKEND_ROOT = Path(__file__).resolve().parent.parent


def _default_data_dir() -> Path:
    """Repo-root `data/` locally; `/srv/data` in the Docker image (sibling of `/srv/backend`)."""
    return BACKEND_ROOT.parent / "data"


class Settings(BaseSettings):
    """Central configuration. Override any field with env vars or a .env file."""

    model_config = SettingsConfigDict(
        env_file=str(BACKEND_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Runtime environment ---
    # development | production (also accepts "prod"). Controls demo-token seeding.
    app_env: str = "development"

    # --- Database ---
    # SQLite by default for local MVP; set DATABASE_URL to a Postgres DSN for prod.
    database_url: str = f"sqlite:///{BACKEND_ROOT / 'pathology_explainer.db'}"

    # --- Auth / sessions ---
    session_ttl_hours: int = 72
    # Cookie name for browser clients; also accepted as X-Session-Token header.
    session_cookie_name: str = "pathology_session"

    # Demo invite tokens (optional). In production, omit these to skip seeding
    # known default tokens — never ship DEMO_* defaults to a public deploy.
    demo_admin_token: str = ""
    demo_annotator_token: str = ""
    demo_clinician_token: str = ""

    # --- LLM provider (provider-agnostic) ---
    # LLM_PROVIDER: "mock" (default, no API key) | "xai" (Grok) | "openai"
    # When a hosted provider is selected but no key is set, the factory falls
    # back to mock so local demos keep working.
    llm_provider: str = "mock"
    # Empty / placeholder → provider-specific default
    # (xai → grok-4.20-0309-non-reasoning, openai → gpt-4o-mini)
    llm_model: str = "mock-heuristic-v1"
    llm_api_key: str = ""
    # Empty → provider-specific default (xai → https://api.x.ai/v1)
    llm_base_url: str = ""
    # Optional alias for xAI (also read from env XAI_API_KEY). Prefer LLM_API_KEY.
    xai_api_key: str = ""
    # HTTP timeout for hosted LLM calls (seconds). Reasoning models may need more.
    llm_timeout_seconds: float = 120.0

    # --- OCR (scan → text) ---
    # OCR_ENGINE: tesseract (default, free) | xai_vision | mock
    ocr_engine: str = "tesseract"
    # Max pages to OCR per report (keep bounded for cost/latency).
    ocr_max_pages: int = 2
    # Vision model override (empty → use LLM_MODEL / xAI default).
    ocr_vision_model: str = ""
    # image detail for xAI vision: low (cheap) | high | auto
    ocr_vision_detail: str = "low"
    # Concurrent Tesseract jobs (Render free ≈512 MB — keep at 1).
    # Peak RSS per job is roughly 150–250 MB on our 1400px page images.
    ocr_max_concurrent: int = 1
    # Extra callers allowed to wait for a slot; beyond this → HTTP 429.
    ocr_max_queue: int = 2

    # --- CORS ---
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # --- Rate limiting (public explain endpoints) ---
    rate_limit_explain: str = "30/minute"
    # When true (e.g. behind Render), use X-Forwarded-For / X-Real-IP for the
    # client identity. Leave false locally so clients cannot spoof the limiter key.
    trust_proxy_headers: bool = False

    # --- Paths ---
    # DATA_DIR overrides the default (sibling of backend/: repo-root/data or /srv/data).
    data_dir: Path = _default_data_dir()
    prompts_dir: Path = BACKEND_ROOT / "prompts"
    config_dir: Path = BACKEND_ROOT / "config"
    docs_dir: Path = BACKEND_ROOT / "docs"

    # --- Seed on startup ---
    seed_on_startup: bool = True

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.app_env.strip().lower() in {"production", "prod"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
