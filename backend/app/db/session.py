"""Engine and session management.

The engine is created lazily from settings (or explicitly by tests). Every request gets its own
``Session`` through the :func:`get_db` dependency; background workers create their own sessions via
:meth:`Database.session`.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool


def build_engine(
    url: str,
    *,
    echo: bool = False,
    pool_size: int = 10,
    max_overflow: int = 20,
    pool_timeout: int = 30,
    statement_timeout_ms: int | None = 60_000,
) -> Engine:
    """Create an engine with safe defaults for PostgreSQL (and SQLite for tests)."""
    kwargs: dict[str, Any] = {"echo": echo, "pool_pre_ping": True}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
        if ":memory:" in url or url.rstrip("/") in {"sqlite:", "sqlite+pysqlite:"}:
            kwargs["poolclass"] = StaticPool
    else:
        kwargs.update(pool_size=pool_size, max_overflow=max_overflow, pool_timeout=pool_timeout)
        if statement_timeout_ms:
            # Server-side statement timeout bounds runaway queries (SEC-08).
            kwargs["connect_args"] = {"options": f"-c statement_timeout={int(statement_timeout_ms)}"}
    engine = create_engine(url, **kwargs)

    if url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def _enable_sqlite_foreign_keys(dbapi_connection: Any, _record: Any) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


class Database:
    """Holds the engine and the session factory for the running process."""

    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        self.session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    @contextmanager
    def session(self) -> Iterator[Session]:
        """Context-managed session that rolls back on error and always closes."""
        session = self.session_factory()
        try:
            yield session
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def dispose(self) -> None:
        self.engine.dispose()


_database: Database | None = None


def init_database(database: Database) -> None:
    global _database
    _database = database


def get_database() -> Database:
    if _database is None:
        raise RuntimeError("database has not been initialised; call init_database() during startup")
    return _database


def get_db() -> Iterator[Session]:
    """FastAPI dependency yielding a request-scoped session."""
    with get_database().session() as session:
        yield session
