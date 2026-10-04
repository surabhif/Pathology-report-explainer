"""Pytest fixtures: isolated SQLite DB + AsyncClient.

Tests set SEED_ON_STARTUP=false and use a temp database so they do not
touch the developer's local pathology_explainer.db.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

# Configure env BEFORE importing app modules that cache settings.
TEST_DB = "sqlite://"  # in-memory; StaticPool keeps one connection
os.environ["DATABASE_URL"] = TEST_DB
os.environ["SEED_ON_STARTUP"] = "false"
os.environ["LLM_PROVIDER"] = "mock"
os.environ["LLM_MODEL"] = "mock-heuristic-v1"

# Clear settings cache if already imported
from app.config import get_settings

get_settings.cache_clear()

from app.db import Base, get_db  # noqa: E402
from app.main import create_app  # noqa: E402
from app.models import User  # noqa: E402
from app.seed import SAMPLE_REPORTS, seed_all  # noqa: E402
import app.models  # noqa: E402, F401


@pytest.fixture()
def engine():
    # StaticPool: share the same in-memory DB across connections
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(bind=eng)
    yield eng
    Base.metadata.drop_all(bind=eng)
    eng.dispose()


@pytest.fixture()
def db_session(engine) -> Iterator[Session]:
    TestSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = TestSession()
    try:
        yield session
    finally:
        session.close()


@pytest_asyncio.fixture()
async def app(engine, db_session):
    """App wired to the test engine; seed demo data once."""
    TestSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    # Seed using a dedicated session
    seed_session = TestSession()
    try:
        await seed_all(seed_session)
    finally:
        seed_session.close()

    application = create_app()

    def _override_get_db():
        session = TestSession()
        try:
            yield session
        finally:
            session.close()

    application.dependency_overrides[get_db] = _override_get_db
    yield application
    application.dependency_overrides.clear()


@pytest_asyncio.fixture()
async def client(app) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def redeem(client: AsyncClient, token: str) -> str:
    resp = await client.post("/api/auth/redeem", json={"token": token})
    assert resp.status_code == 200, resp.text
    return resp.json()["session_token"]


@pytest_asyncio.fixture()
async def admin_headers(client: AsyncClient) -> dict[str, str]:
    token = await redeem(client, "DEMO_ADMIN_TOKEN")
    return {"X-Session-Token": token}


@pytest_asyncio.fixture()
async def annotator_headers(client: AsyncClient) -> dict[str, str]:
    token = await redeem(client, "DEMO_ANNOTATOR_TOKEN")
    return {"X-Session-Token": token}


@pytest_asyncio.fixture()
async def clinician_headers(client: AsyncClient) -> dict[str, str]:
    token = await redeem(client, "DEMO_CLINICIAN_TOKEN")
    return {"X-Session-Token": token}
