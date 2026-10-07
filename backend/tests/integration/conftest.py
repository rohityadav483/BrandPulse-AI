"""Shared PostgreSQL fixtures for the Phase 3.2 DB tests (skipped without TEST_DATABASE_URL).

Older integration files keep their own copies; these are used by the content_items tests.
"""

import os
import uuid
from contextlib import contextmanager
from datetime import date
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app.db.session import normalize_url

ADMIN_URL = os.environ.get("TEST_DATABASE_URL")
ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"


@contextmanager
def _blank_database():
    name = f"bp_p32test_{uuid.uuid4().hex[:12]}"
    server_url = normalize_url(ADMIN_URL)
    admin = create_engine(server_url, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    url = make_url(server_url).set(database=name).render_as_string(hide_password=False)
    try:
        yield url
    finally:
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
        admin.dispose()


@pytest.fixture
def migrated_engine():
    """A blank database upgraded to head, one per test."""
    if not ADMIN_URL:
        pytest.skip("TEST_DATABASE_URL not set (needs a PostgreSQL server)")
    with _blank_database() as url:
        cfg = Config(str(ALEMBIC_INI))
        cfg.attributes["url"] = url
        command.upgrade(cfg, "head")
        engine = create_engine(url)
        yield engine
        engine.dispose()


@pytest.fixture
def new_brand(migrated_engine):
    def _make(name: str = "Samsung") -> uuid.UUID:
        with migrated_engine.begin() as conn:
            return conn.execute(
                text("INSERT INTO brands (name, normalized_name) VALUES (:n, :nn) RETURNING id"),
                {"n": name, "nn": name.lower()},
            ).scalar_one()

    return _make


@pytest.fixture
def new_analysis(migrated_engine):
    def _make(brand_id: uuid.UUID) -> uuid.UUID:
        with migrated_engine.begin() as conn:
            return conn.execute(
                text(
                    "INSERT INTO analyses (brand_id, as_of_date, current_start, current_end, "
                    "baseline_start, baseline_end) VALUES (:b, :a, :cs, :ce, :bs, :be) "
                    "RETURNING id"
                ),
                {
                    "b": brand_id,
                    "a": date(2026, 8, 10),
                    "cs": date(2026, 7, 12),
                    "ce": date(2026, 8, 10),
                    "bs": date(2026, 6, 12),
                    "be": date(2026, 7, 11),
                },
            ).scalar_one()

    return _make
