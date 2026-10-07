"""Database engine and connectivity check. No models or migrations yet."""

import logging

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)

_engines: dict[str, Engine] = {}


def normalize_url(url: str) -> str:
    """Point plain Postgres URLs (as Supabase gives them) at the psycopg 3 driver."""
    for prefix in ("postgresql://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix) :]
    return url


def get_engine(url: str) -> Engine:
    if url not in _engines:
        normalized = normalize_url(url)
        kwargs: dict = {"pool_pre_ping": True}
        if normalized.startswith("postgresql"):
            # prepare_threshold=None keeps Supabase's transaction pooler happy (DATABASE.md §2).
            kwargs["connect_args"] = {"connect_timeout": 3, "prepare_threshold": None}
        _engines[url] = create_engine(normalized, **kwargs)
    return _engines[url]


def check_database(url: str) -> bool:
    """True if `SELECT 1` succeeds. Never raises, never logs the URL (it holds the password)."""
    if not url:
        return False
    try:
        with get_engine(url).connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except SQLAlchemyError as exc:
        logger.warning(
            "database_check_failed", extra={"error_type": type(exc).__name__}
        )
        return False


def dispose_engines() -> None:
    """Close pooled connections (called on shutdown)."""
    for engine in _engines.values():
        engine.dispose()
    _engines.clear()
