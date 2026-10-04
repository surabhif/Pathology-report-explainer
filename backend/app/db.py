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
    """Add columns if an older DB was created before they existed.

    create_all() does not ALTER existing tables; this keeps Neon/Render deploys
    working without a manual migration step for additive Generation columns.
    """
    ddl_sqlite = [
        ("is_fallback", "ALTER TABLE generations ADD COLUMN is_fallback BOOLEAN DEFAULT 0 NOT NULL"),
        ("fallback_reason", "ALTER TABLE generations ADD COLUMN fallback_reason VARCHAR(128)"),
        ("requested_provider", "ALTER TABLE generations ADD COLUMN requested_provider VARCHAR(64)"),
        ("requested_model", "ALTER TABLE generations ADD COLUMN requested_model VARCHAR(128)"),
        ("explanation_retried", "ALTER TABLE generations ADD COLUMN explanation_retried BOOLEAN DEFAULT 0 NOT NULL"),
        ("grounding_check_json", "ALTER TABLE generations ADD COLUMN grounding_check_json JSON"),
        ("text_source", "ALTER TABLE generations ADD COLUMN text_source VARCHAR(32) DEFAULT 'reference' NOT NULL"),
        ("ocr_run_id", "ALTER TABLE generations ADD COLUMN ocr_run_id INTEGER"),
    ]
    ddl_pg = [
        ("is_fallback", "ALTER TABLE generations ADD COLUMN is_fallback BOOLEAN DEFAULT FALSE NOT NULL"),
        ("fallback_reason", "ALTER TABLE generations ADD COLUMN fallback_reason VARCHAR(128)"),
        ("requested_provider", "ALTER TABLE generations ADD COLUMN requested_provider VARCHAR(64)"),
        ("requested_model", "ALTER TABLE generations ADD COLUMN requested_model VARCHAR(128)"),
        (
            "explanation_retried",
            "ALTER TABLE generations ADD COLUMN explanation_retried BOOLEAN DEFAULT FALSE NOT NULL",
        ),
        ("grounding_check_json", "ALTER TABLE generations ADD COLUMN grounding_check_json JSON"),
        (
            "text_source",
            "ALTER TABLE generations ADD COLUMN text_source VARCHAR(32) DEFAULT 'reference' NOT NULL",
        ),
        ("ocr_run_id", "ALTER TABLE generations ADD COLUMN ocr_run_id INTEGER"),
    ]
    with engine.begin() as conn:
        if engine.url.get_backend_name() == "sqlite":
            existing = {row[1] for row in conn.execute(text("PRAGMA table_info(generations)")).fetchall()}
            statements = ddl_sqlite
        else:
            rows = conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'generations'"
                )
            ).fetchall()
            existing = {r[0] for r in rows}
            statements = ddl_pg
        for col, statement in statements:
            if col not in existing:
                conn.execute(text(statement))


def _ensure_report_scan_column() -> None:
    """Add reports.scan_manifest if missing (older DBs)."""
    with engine.begin() as conn:
        if engine.url.get_backend_name() == "sqlite":
            existing = {row[1] for row in conn.execute(text("PRAGMA table_info(reports)")).fetchall()}
            if "scan_manifest" not in existing:
                conn.execute(text("ALTER TABLE reports ADD COLUMN scan_manifest JSON"))
        else:
            rows = conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'reports'"
                )
            ).fetchall()
            existing = {r[0] for r in rows}
            if "scan_manifest" not in existing:
                conn.execute(text("ALTER TABLE reports ADD COLUMN scan_manifest JSON"))


def init_db() -> None:
    """Create tables if they do not exist (MVP convenience; prefer Alembic in prod)."""
    # Import models so metadata is populated before create_all.
    import app.models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    try:
        _ensure_generation_fallback_columns()
        _ensure_report_scan_column()
    except Exception:  # noqa: BLE001 — best-effort schema patch on startup
        # Table may not exist yet on a brand-new empty DB before create_all,
        # or the dialect may differ; create_all already covered new installs.
        pass
