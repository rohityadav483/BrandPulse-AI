"""Migration tests against a real, blank PostgreSQL database.

Set TEST_DATABASE_URL to a server URL whose role may CREATE DATABASE, e.g.
postgresql://user:pass@localhost:5432/postgres. Each test run creates (and drops) its own
throwaway database, so nothing existing is touched.
"""

import datetime as dt
import os
import uuid
from contextlib import contextmanager
from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DataError, IntegrityError

from app.db.models import Base
from app.db.session import normalize_url

ADMIN_URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not ADMIN_URL, reason="TEST_DATABASE_URL not set (needs a PostgreSQL server)"
)

ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"

# Independent copy of docs/DATABASE.md section 3 (so the migration is checked against the doc).
EXPECTED_ENUMS = {
    "analysis_status": ["queued", "running", "completed", "partial", "failed"],
    "analysis_stage": [
        "planning",
        "collecting",
        "processing",
        "analyzing",
        "detecting",
        "snapshotting",
        "done",
    ],
    "brand_role": ["target", "competitor", "suggested"],
    "source_type": ["web", "news", "youtube", "forum", "shopping"],
    "window_kind": ["baseline", "current"],
    "content_purpose": ["collection", "investigation"],
    "date_confidence": ["exact", "approximate", "unknown"],
    "sentiment": ["positive", "neutral", "negative"],
    "signal_kind": ["aspect_negative_spike"],
    "impact_level": ["low", "medium", "high"],
    "signal_status": ["detected", "investigating", "investigated"],
    "investigation_status": ["queued", "running", "completed", "failed"],
    "investigation_step": [
        "generating_queries",
        "collecting_evidence",
        "scoring_evidence",
        "comparing_competitors",
        "synthesizing",
        "recommending",
        "done",
    ],
    "scope_verdict": ["brand_specific", "industry_wide", "inconclusive", "unknown"],
    "stance": ["supports", "contradicts", "neutral"],
    "priority": ["low", "medium", "high"],
    "llm_call_status": ["ok", "retry", "rate_limited", "invalid_json", "failed"],
}


def _cfg(url: str) -> Config:
    cfg = Config(str(ALEMBIC_INI))
    cfg.attributes["url"] = url
    return cfg


@contextmanager
def blank_database():
    name = f"bp_migtest_{uuid.uuid4().hex[:12]}"
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


@pytest.fixture(scope="module")
def migrated():
    """A blank database upgraded to head once, shared by the read-only schema tests."""
    with blank_database() as url:
        command.upgrade(_cfg(url), "head")
        engine = create_engine(url)
        yield engine
        engine.dispose()


@pytest.fixture
def conn(migrated):
    """Per-test connection; everything rolls back so tests stay independent."""
    with migrated.connect() as connection:
        trans = connection.begin()
        yield connection
        trans.rollback()


def _rows(conn, sql, **params):
    return conn.execute(text(sql), params).fetchall()


def _new_brand(conn, name="Samsung") -> uuid.UUID:
    return conn.execute(
        text("INSERT INTO brands (name, normalized_name) VALUES (:n, :nn) RETURNING id"),
        {"n": name, "nn": name.lower()},
    ).scalar_one()


def _new_analysis(conn, brand_id, **overrides) -> uuid.UUID:
    values = {
        "brand_id": brand_id,
        "as_of_date": dt.date(2026, 8, 10),
        "current_start": dt.date(2026, 7, 12),
        "current_end": dt.date(2026, 8, 10),
        "baseline_start": dt.date(2026, 6, 12),
        "baseline_end": dt.date(2026, 7, 11),
    } | overrides
    cols = ", ".join(values)
    params = ", ".join(f":{k}" for k in values)
    return conn.execute(
        text(f"INSERT INTO analyses ({cols}) VALUES ({params}) RETURNING id"), values
    ).scalar_one()


# ---------- schema shape ----------


def test_upgrade_head_on_blank_database(migrated):
    with migrated.connect() as c:
        assert _rows(c, "SELECT version_num FROM alembic_version") == [("0002",)]


def test_only_phase_0_and_2_tables_exist(migrated):
    with migrated.connect() as c:
        tables = {
            r[0] for r in _rows(c, "SELECT tablename FROM pg_tables WHERE schemaname='public'")
        }
    assert tables == {
        "alembic_version",
        "brands",
        "analyses",
        "analysis_brands",
        "serp_cache",
        "serp_usage",
    }


def test_all_enums_exist_with_exact_ordered_values(migrated):
    with migrated.connect() as c:
        rows = _rows(
            c,
            """SELECT t.typname, e.enumlabel
               FROM pg_type t JOIN pg_enum e ON e.enumtypid = t.oid
               ORDER BY t.typname, e.enumsortorder""",
        )
    found: dict[str, list[str]] = {}
    for typname, label in rows:
        found.setdefault(typname, []).append(label)
    assert found == EXPECTED_ENUMS


def test_models_match_migrated_schema(migrated):
    with migrated.connect() as c:
        ctx = MigrationContext.configure(c, opts={"compare_type": True})
        assert compare_metadata(ctx, Base.metadata) == []


def test_indexes_match_database_md(migrated):
    with migrated.connect() as c:
        defs = {
            r[0]: r[1]
            for r in _rows(
                c, "SELECT indexname, indexdef FROM pg_indexes WHERE schemaname='public'"
            )
        }
    assert "(created_at DESC)" in defs["ix_analyses_created_at"]
    assert "(client_ip_hash, created_at)" in defs["ix_analyses_client_ip_hash_created_at"]
    assert "(status)" in defs["ix_analyses_status"]
    one_target = defs["uq_analysis_brands_one_target"]
    assert "UNIQUE" in one_target and "(analysis_id)" in one_target and "'target'" in one_target
    assert "pk_analysis_brands" in defs and "pk_brands" in defs and "pk_analyses" in defs


# ---------- brands ----------


def test_brand_defaults_and_unique_normalized_name(conn):
    row = conn.execute(
        text(
            "INSERT INTO brands (name, normalized_name) VALUES ('Samsung', 'samsung') "
            "RETURNING id, created_at"
        )
    ).one()
    assert isinstance(row.id, uuid.UUID) and row.created_at is not None
    with pytest.raises(IntegrityError), conn.begin_nested():
        conn.execute(
            text("INSERT INTO brands (name, normalized_name) VALUES ('SAMSUNG ', 'samsung')")
        )


def test_brand_requires_name_and_normalized_name(conn):
    with pytest.raises(IntegrityError), conn.begin_nested():
        conn.execute(text("INSERT INTO brands (name) VALUES ('x')"))
    with pytest.raises(IntegrityError), conn.begin_nested():
        conn.execute(text("INSERT INTO brands (normalized_name) VALUES ('x')"))


# ---------- analyses ----------


def test_analysis_defaults(conn):
    aid = _new_analysis(conn, _new_brand(conn))
    row = conn.execute(text("SELECT * FROM analyses WHERE id = :i"), {"i": aid}).mappings().one()
    assert row["status"] == "queued"
    assert row["stage"] is None
    assert row["progress"] == 0
    assert row["period_days"] == 30
    assert row["category"] == "consumer_electronics"
    assert row["warnings"] == []
    assert row["serp_calls_used"] == 0
    assert row["serp_calls_budget"] == 12
    assert row["live_run"] is False
    assert row["created_at"] is not None
    assert row["product"] is None and row["error"] is None and row["client_ip_hash"] is None
    assert row["started_at"] is None and row["finished_at"] is None


def test_analysis_requires_window_dates_and_brand(conn):
    brand = _new_brand(conn)
    with pytest.raises(IntegrityError), conn.begin_nested():
        conn.execute(
            text("INSERT INTO analyses (brand_id, as_of_date) VALUES (:b, '2026-08-10')"),
            {"b": brand},
        )
    with pytest.raises(IntegrityError), conn.begin_nested():
        _new_analysis(conn, uuid.uuid4())  # unknown brand


@pytest.mark.parametrize("days", [7, 14, 30])
def test_period_days_allowed(conn, days):
    _new_analysis(conn, _new_brand(conn), period_days=days)


@pytest.mark.parametrize("days", [0, 1, 10, 31, 60])
def test_period_days_rejected(conn, days):
    with pytest.raises(IntegrityError), conn.begin_nested():
        _new_analysis(conn, _new_brand(conn), period_days=days)


@pytest.mark.parametrize("progress", [0, 50, 100])
def test_progress_allowed(conn, progress):
    _new_analysis(conn, _new_brand(conn), progress=progress)


@pytest.mark.parametrize("progress", [-1, 101])
def test_progress_rejected(conn, progress):
    with pytest.raises(IntegrityError), conn.begin_nested():
        _new_analysis(conn, _new_brand(conn), progress=progress)


def test_product_max_80_chars(conn):
    brand = _new_brand(conn)
    _new_analysis(conn, brand, product="x" * 80)
    with pytest.raises(IntegrityError), conn.begin_nested():
        _new_analysis(conn, brand, product="x" * 81)


def test_status_and_stage_reject_unknown_values(conn):
    brand = _new_brand(conn)
    with pytest.raises(DataError), conn.begin_nested():
        _new_analysis(conn, brand, status="bogus")
    with pytest.raises(DataError), conn.begin_nested():
        _new_analysis(conn, brand, stage="bogus")
    aid = _new_analysis(conn, brand, status="partial", stage="snapshotting")
    row = conn.execute(text("SELECT status, stage FROM analyses WHERE id=:i"), {"i": aid}).one()
    assert (row.status, row.stage) == ("partial", "snapshotting")


# ---------- analysis_brands ----------


def _link(conn, analysis_id, brand_id, role):
    conn.execute(
        text("INSERT INTO analysis_brands (analysis_id, brand_id, role) VALUES (:a, :b, :r)"),
        {"a": analysis_id, "b": brand_id, "r": role},
    )


def test_one_target_per_analysis_but_many_competitors(conn):
    aid = _new_analysis(conn, _new_brand(conn, "Samsung"))
    _link(conn, aid, _new_brand(conn, "Target Brand"), "target")
    _link(conn, aid, _new_brand(conn, "Apple"), "competitor")
    _link(conn, aid, _new_brand(conn, "OnePlus"), "suggested")
    with pytest.raises(IntegrityError), conn.begin_nested():
        _link(conn, aid, _new_brand(conn, "Second Target"), "target")


def test_target_unique_is_per_analysis(conn):
    brand = _new_brand(conn)
    a1 = _new_analysis(conn, brand)
    a2 = _new_analysis(conn, brand)
    _link(conn, a1, brand, "target")
    _link(conn, a2, brand, "target")  # same brand may be target of another analysis


def test_same_brand_cannot_link_twice_to_one_analysis(conn):
    brand = _new_brand(conn)
    aid = _new_analysis(conn, brand)
    _link(conn, aid, brand, "target")
    with pytest.raises(IntegrityError), conn.begin_nested():
        _link(conn, aid, brand, "competitor")


def test_role_rejects_unknown_value(conn):
    brand = _new_brand(conn)
    aid = _new_analysis(conn, brand)
    with pytest.raises(DataError), conn.begin_nested():
        _link(conn, aid, brand, "rival")


def test_deleting_analysis_cascades_to_analysis_brands(conn):
    brand = _new_brand(conn)
    aid = _new_analysis(conn, brand)
    _link(conn, aid, brand, "target")
    _link(conn, aid, _new_brand(conn, "Apple"), "competitor")
    conn.execute(text("DELETE FROM analyses WHERE id = :i"), {"i": aid})
    assert _rows(conn, "SELECT 1 FROM analysis_brands WHERE analysis_id = :i", i=aid) == []
    # brands are never cascade-deleted
    assert _rows(conn, "SELECT count(*) FROM brands WHERE id = :b", b=brand) == [(1,)]


def test_brands_are_never_cascade_deleted(conn):
    brand = _new_brand(conn)
    aid = _new_analysis(conn, brand)
    _link(conn, aid, brand, "target")
    with pytest.raises(IntegrityError), conn.begin_nested():
        conn.execute(text("DELETE FROM brands WHERE id = :b"), {"b": brand})


# ---------- downgrade / re-upgrade ----------


def test_downgrade_to_base_then_upgrade_again():
    with blank_database() as url:
        cfg = _cfg(url)
        command.upgrade(cfg, "head")
        command.downgrade(cfg, "base")
        engine = create_engine(url)
        with engine.connect() as c:
            tables = {
                r[0] for r in _rows(c, "SELECT tablename FROM pg_tables WHERE schemaname='public'")
            }
            enums = _rows(c, "SELECT typname FROM pg_type WHERE typtype = 'e'")
        assert tables == {"alembic_version"}
        assert enums == []
        command.upgrade(cfg, "head")
        with engine.connect() as c:
            assert _rows(c, "SELECT version_num FROM alembic_version") == [("0002",)]
        engine.dispose()


# ---------- Phase 2: serp_cache / serp_usage ----------


def _insert_usage(conn, **overrides):
    values = {
        "cache_key": "k",
        "engine": "google",
        "cache_hit": False,
        "credits": 1,
        "purpose": "analysis",
        "account_label": "acct",
    } | overrides
    cols = ", ".join(values)
    params = ", ".join(f":{k}" for k in values)
    return conn.execute(
        text(f"INSERT INTO serp_usage ({cols}) VALUES ({params}) RETURNING id"), values
    ).scalar_one()


def test_serp_cache_defaults(conn):
    conn.execute(
        text(
            "INSERT INTO serp_cache (cache_key, engine, params, response, expires_at) "
            "VALUES ('k1', 'google', '{}', '{}', now())"
        )
    )
    row = _rows(conn, "SELECT pinned, fetched_at IS NOT NULL, http_status FROM serp_cache")
    assert row == [(False, True, None)]


def test_serp_usage_defaults_and_bigserial_id(conn):
    first = _insert_usage(conn)
    second = _insert_usage(conn)
    assert second == first + 1
    assert _rows(conn, "SELECT created_at IS NOT NULL, analysis_id FROM serp_usage LIMIT 1") == [
        (True, None)
    ]


@pytest.mark.parametrize("credits", [-1, 2])
def test_serp_usage_credits_must_be_zero_or_one(conn, credits):
    with pytest.raises(IntegrityError), conn.begin_nested():
        _insert_usage(conn, credits=credits)


def test_serp_usage_purpose_is_restricted(conn):
    for purpose in ("analysis", "investigation", "fixture_recording", "probe"):
        _insert_usage(conn, purpose=purpose)
    with pytest.raises(IntegrityError), conn.begin_nested():
        _insert_usage(conn, purpose="other")


def test_deleting_an_analysis_keeps_usage_rows(conn):
    brand = _new_brand(conn)
    aid = _new_analysis(conn, brand)
    _insert_usage(conn, analysis_id=aid)
    conn.execute(text("DELETE FROM analyses WHERE id = :a"), {"a": aid})
    assert _rows(conn, "SELECT count(*), count(analysis_id) FROM serp_usage") == [(1, 0)]


def test_serp_indexes_exist(migrated):
    with migrated.connect() as c:
        rows = _rows(c, "SELECT indexname FROM pg_indexes WHERE schemaname='public'")
    names = {r[0] for r in rows}
    assert {"ix_serp_cache_expires_at", "ix_serp_usage_created_at"} <= names


def test_downgrade_one_step_returns_to_phase_0_schema():
    with blank_database() as url:
        cfg = _cfg(url)
        command.upgrade(cfg, "head")
        command.downgrade(cfg, "-1")
        engine = create_engine(url)
        with engine.connect() as c:
            tables = {
                r[0] for r in _rows(c, "SELECT tablename FROM pg_tables WHERE schemaname='public'")
            }
            assert _rows(c, "SELECT version_num FROM alembic_version") == [("0001",)]
        assert tables == {"alembic_version", "brands", "analyses", "analysis_brands"}
        engine.dispose()
