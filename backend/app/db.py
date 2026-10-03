"""SQLAlchemy engine, session factory, and Base.

MVP note: we call Base.metadata.create_all() on startup for simplicity.
An Alembic initial migration is also provided under alembic/versions/ for
Postgres-ready deployments — use `alembic upgrade head` instead of create_all
when you prefer migration-managed schema.
"""

from collections.abc import Generator

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


def _make_engine():
    settings = get_settings()
    url = settings.database_url
    connect_args = {}
    # SQLite needs check_same_thread=False for FastAPI's multi-thread request handling.
    if url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    # pool_pre_ping: Neon (and most serverless Postgres) drops idle connections
    # (~5 minutes). Ping before checkout so the first request after idle succeeds.
    engine = create_engine(
        url,
        connect_args=connect_args,
        future=True,
        pool_pre_ping=True,
    )

    # Enable FK constraints on SQLite (off by default).
    if url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def _set_sqlite_pragma(dbapi_conn, _connection_record):  # noqa: ANN001
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


engine = _make_engine()
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, class_=Session)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a DB session and closes it after the request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _ensure_generation_fallback_columns() -> None:
    """Add fallback-label columns if an older DB was created before they existed.

    create_all() does not ALTER existing tables; this keeps Neon/Render deploys
    working without a manual migration step for these four columns.
    """
    ddl = [
        ("is_fallback", "ALTER TABLE generations ADD COLUMN is_fallback BOOLEAN DEFAULT 0 NOT NULL"),
        ("fallback_reason", "ALTER TABLE generations ADD COLUMN fallback_reason VARCHAR(128)"),
        ("requested_provider", "ALTER TABLE generations ADD COLUMN requested_provider VARCHAR(64)"),
        ("requested_model", "ALTER TABLE generations ADD COLUMN requested_model VARCHAR(128)"),
    ]
    with engine.begin() as conn:
        existing = {row[1] for row in conn.execute(text("PRAGMA table_info(generations)")).fetchall()} if engine.url.get_backend_name() == "sqlite" else None
        if existing is None:
            # Postgres / others: ask information_schema
            rows = conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'generations'"
                )
            ).fetchall()
            existing = {r[0] for r in rows}
        for col, statement in ddl:
            if col not in existing:
                # Postgres boolean default: use FALSE instead of 0 when not sqlite
                stmt = statement
                if engine.url.get_backend_name() != "sqlite" and col == "is_fallback":
                    stmt = (
                        "ALTER TABLE generations ADD COLUMN is_fallback "
                        "BOOLEAN DEFAULT FALSE NOT NULL"
                    )
                conn.execute(text(stmt))


def init_db() -> None:
    """Create tables if they do not exist (MVP convenience; prefer Alembic in prod)."""
    # Import models so metadata is populated before create_all.
    import app.models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    try:
        _ensure_generation_fallback_columns()
    except Exception:  # noqa: BLE001 — best-effort schema patch on startup
        # Table may not exist yet on a brand-new empty DB before create_all,
        # or the dialect may differ; create_all already covered new installs.
        pass
