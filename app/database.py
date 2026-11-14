"""Database engine and session plumbing.

SQLite is the default so the project clones and runs with no services. Set
DATABASE_URL to a PostgreSQL DSN and the same code uses it — nothing is
SQLite-specific other than the connect arguments.
"""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    pass


def _engine_kwargs(url: str) -> dict:
    if url.startswith("sqlite"):
        # FastAPI serves requests from a thread pool, so the default
        # single-thread guard has to be relaxed.
        return {"connect_args": {"check_same_thread": False, "timeout": 15}}
    return {"pool_pre_ping": True, "pool_size": 5, "max_overflow": 10}


engine = create_engine(settings.database_url, future=True, **_engine_kwargs(settings.database_url))

if settings.database_url.startswith("sqlite"):

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_connection, _record) -> None:  # noqa: ANN001
        cursor = dbapi_connection.cursor()
        # WAL lets the background synthesis worker write while a request reads.
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


def get_db() -> Iterator[Session]:
    """FastAPI dependency: one session per request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create tables. Fine for a single deploy; use Alembic before real traffic."""
    from app import models  # noqa: F401  - import registers the mappers

    Base.metadata.create_all(bind=engine)
