"""FastAPI application entrypoint.

Run from backend/:
  uvicorn app.main:app --reload

Or from repo root:
  uvicorn app.main:app --reload --app-dir backend

MVP schema: create_all on startup (+ optional Alembic migration for Postgres).
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.config import get_settings
from app.db import SessionLocal, init_db
from app.routers import admin, annotate, auth_routes, public, results, review
from app.routers.public import limiter
from app.seed import seed_all

# PHI policy: keep logs at INFO with structured ids — never attach report_text.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("app.main")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings = get_settings()
    init_db()
    if settings.seed_on_startup:
        db = SessionLocal()
        try:
            await seed_all(db)
        finally:
            db.close()
    logger.info(
        "startup complete provider=%s db=%s",
        settings.llm_provider,
        settings.database_url.split("://", 1)[0],
    )
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Pathology Report Explainer MVP",
        description=(
            "Extract structured pathology facts and generate grounded plain-language "
            "explanations with evaluation checks. Demo invite tokens: "
            "DEMO_ADMIN_TOKEN, DEMO_ANNOTATOR_TOKEN, DEMO_CLINICIAN_TOKEN."
        ),
        version="0.1.0",
        lifespan=lifespan,
    )

    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(auth_routes.router)
    app.include_router(public.router)
    app.include_router(admin.router)
    app.include_router(annotate.router)
    app.include_router(review.router)
    app.include_router(results.router)

    @app.get("/api/health")
    def health() -> dict:
        return {"ok": True, "provider": settings.llm_provider}

    @app.get("/api/about")
    def about() -> dict:
        """Static about content from docs/ABOUT.md (fallback inline)."""
        about_path = settings.docs_dir / "ABOUT.md"
        if about_path.exists():
            body = about_path.read_text(encoding="utf-8")
        else:
            body = (
                "# Pathology Report Explainer MVP\n\n"
                "This tool extracts structured facts from pathology reports and "
                "explains them in plain language with grounding quotes. "
                "It is a research prototype — not for clinical decision-making."
            )
        return {"title": "Pathology Report Explainer MVP", "body": body}

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception) -> JSONResponse:
        # Avoid leaking PHI or stack traces with report content in responses.
        logger.exception("unhandled path=%s err=%s", request.url.path, type(exc).__name__)
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})

    return app


app = create_app()
