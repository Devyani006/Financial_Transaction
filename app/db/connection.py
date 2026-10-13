"""
app/db/connection.py — Database Connection Management
======================================================
Why SQLAlchemy engine + connection pool?
  Rather than opening a new database connection for every query (expensive),
  SQLAlchemy maintains a pool of reusable connections. This module is the
  single place where connections are created — everywhere else just borrows
  from the pool and returns connections automatically via context managers.

  Using `text()` with bound parameters prevents SQL injection: the driver
  sends the query and parameters separately, so user input can never alter
  the query structure.
"""

import logging
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, text, event
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.exc import OperationalError, SQLAlchemyError

from app.config import settings

logger = logging.getLogger(__name__)

# ── Engine creation ────────────────────────────────────────────────────────────
# pool_recycle=3600: recycle connections every hour to avoid MySQL's
#   "wait_timeout" dropping idle connections.
# pool_pre_ping=True: test each connection before using it (handles stale connections).
engine = create_engine(
    settings.db.url,
    pool_recycle=3600,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
    echo=settings.debug,  # logs every SQL query when DEBUG=true
)

# Session factory — used in the FastAPI dependency
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# ── Context managers ──────────────────────────────────────────────────────────

@contextmanager
def get_connection():
    """
    Yield a raw DBAPI connection from the pool.
    Use this for direct SQL execution with pandas.read_sql().
    Always released back to the pool, even on error.
    """
    conn = engine.connect()
    try:
        yield conn
    except SQLAlchemyError as e:
        logger.error("Database error: %s", e)
        raise
    finally:
        conn.close()


@contextmanager
def get_session() -> Generator[Session, None, None]:
    """
    Yield an ORM Session with automatic commit/rollback.
    Use this for write operations or when working with ORM models.
    """
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except SQLAlchemyError as e:
        session.rollback()
        logger.error("Session error, rolling back: %s", e)
        raise
    finally:
        session.close()


# ── FastAPI dependency ─────────────────────────────────────────────────────────

def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency that yields a database session per request.
    FastAPI's dependency injection handles cleanup automatically.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ── Health check ───────────────────────────────────────────────────────────────

def check_connectivity() -> dict:
    """
    Returns a dict with db status and MySQL server version.
    Used by the /health endpoint to distinguish app-up from db-up.
    """
    try:
        with get_connection() as conn:
            result = conn.execute(text("SELECT VERSION() AS version")).fetchone()
            return {"status": "ok", "mysql_version": result.version}
    except OperationalError as e:
        return {"status": "error", "detail": str(e)}
