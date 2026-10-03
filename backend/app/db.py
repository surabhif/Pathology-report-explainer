"""SQLAlchemy engine, session factory, and Base.

MVP note: we call Base.metadata.create_all() on startup for simplicity.
An Alembic initial migration is also provided under alembic/versions/ for
Postgres-ready deployments — use `alembic upgrade head` instead of create_all
when you prefer migration-managed schema.
"""

from collections.abc import Generator

from sqlalchemy import create_engine, event
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
    engine = create_engine(url, connect_args=connect_args, future=True)

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


def init_db() -> None:
    """Create tables if they do not exist (MVP convenience; prefer Alembic in prod)."""
    # Import models so metadata is populated before create_all.
    import app.models  # noqa: F401

    Base.metadata.create_all(bind=engine)
