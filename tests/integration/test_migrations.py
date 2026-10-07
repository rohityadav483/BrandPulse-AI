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
        assert _rows(c, "SELECT version_num FROM alembic_version") == [("0006",)]


def test_only_phase_0_to_4_2_tables_exist(migrated):
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
        "raw_items",
        "content_items",
        "content_analysis",
        "item_aspects",
        "trend_points",
        "brand_snapshots",
        "signals",
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
            assert _rows(c, "SELECT version_num FROM alembic_version") == [("0006",)]
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


def _tables(engine):
    with engine.connect() as c:
        return {r[0] for r in _rows(c, "SELECT tablename FROM pg_tables WHERE schemaname='public'")}


def test_downgrade_to_0004_removes_only_the_nlp_tables():
    with blank_database() as url:
        cfg = _cfg(url)
        command.upgrade(cfg, "head")
        command.downgrade(cfg, "-1")
        engine = create_engine(url)
        with engine.connect() as c:
            assert _rows(c, "SELECT version_num FROM alembic_version") == [("0004",)]
            enums = _rows(c, "SELECT count(*) FROM pg_type WHERE typtype = 'e'")
        assert _tables(engine) == {
            "alembic_version",
            "brands",
            "analyses",
            "analysis_brands",
            "serp_cache",
            "serp_usage",
            "raw_items",
            "content_items",
        }
        assert enums == [(17,)]  # the NLP tables never owned an enum (sentiment is from 0001)
        command.upgrade(cfg, "head")
        assert {"content_analysis", "item_aspects"} <= _tables(engine)
        engine.dispose()


def test_downgrade_to_0003_removes_content_and_nlp_tables():
    with blank_database() as url:
        cfg = _cfg(url)
        command.upgrade(cfg, "head")
        command.downgrade(cfg, "0003")
        engine = create_engine(url)
        with engine.connect() as c:
            assert _rows(c, "SELECT version_num FROM alembic_version") == [("0003",)]
            enums = _rows(c, "SELECT count(*) FROM pg_type WHERE typtype = 'e'")
        assert _tables(engine) == {
            "alembic_version",
            "brands",
            "analyses",
            "analysis_brands",
            "serp_cache",
            "serp_usage",
            "raw_items",
        }
        assert enums == [(17,)]
        engine.dispose()


def test_downgrade_to_0002_removes_raw_content_and_nlp_tables():
    with blank_database() as url:
        cfg = _cfg(url)
        command.upgrade(cfg, "head")
        command.downgrade(cfg, "0002")
        engine = create_engine(url)
        with engine.connect() as c:
            assert _rows(c, "SELECT version_num FROM alembic_version") == [("0002",)]
        assert _tables(engine) == {
            "alembic_version",
            "brands",
            "analyses",
            "analysis_brands",
            "serp_cache",
            "serp_usage",
        }
        command.upgrade(cfg, "head")  # and back up again
        assert {"content_items", "content_analysis", "item_aspects"} <= _tables(engine)
        engine.dispose()


def test_downgrade_to_0001_returns_to_phase_0_schema():
    with blank_database() as url:
        cfg = _cfg(url)
        command.upgrade(cfg, "head")
        command.downgrade(cfg, "0001")
        engine = create_engine(url)
        with engine.connect() as c:
            tables = {
                r[0] for r in _rows(c, "SELECT tablename FROM pg_tables WHERE schemaname='public'")
            }
            assert _rows(c, "SELECT version_num FROM alembic_version") == [("0001",)]
        assert tables == {"alembic_version", "brands", "analyses", "analysis_brands"}
        engine.dispose()


# ---------- Phase 3.1: raw_items ----------

RAW_KEY = "a" * 64


def _new_raw_item(conn, analysis_id, brand_id, **overrides) -> uuid.UUID:
    values = {
        "analysis_id": analysis_id,
        "brand_id": brand_id,
        "purpose": "collection",
        "window": "current",
        "source_type": "web",
        "engine": "google",
        "title": "Galaxy S25 Ultra review",
        "url": "https://reviews.example.test/s25",
        "raw_key": RAW_KEY,
    } | overrides
    cols = ", ".join(f'"{k}"' for k in values)
    params = ", ".join(f":{k}" for k in values)
    return conn.execute(
        text(f"INSERT INTO raw_items ({cols}) VALUES ({params}) RETURNING id"), values
    ).scalar_one()


@pytest.fixture
def ctx(conn):
    brand = _new_brand(conn)
    return conn, _new_analysis(conn, brand), brand


def test_raw_items_columns_match_contract(migrated):
    with migrated.connect() as c:
        rows = _rows(
            c,
            """SELECT column_name, is_nullable, udt_name FROM information_schema.columns
               WHERE table_name = 'raw_items' ORDER BY ordinal_position""",
        )
    assert {name: (null, udt) for name, null, udt in rows} == {
        "id": ("NO", "uuid"),
        "analysis_id": ("NO", "uuid"),
        "brand_id": ("NO", "uuid"),
        "purpose": ("NO", "content_purpose"),
        "window": ("YES", "window_kind"),
        "source_type": ("NO", "source_type"),
        "engine": ("NO", "text"),
        "title": ("NO", "text"),
        "url": ("NO", "text"),
        "snippet": ("YES", "text"),
        "author": ("YES", "text"),
        "published_raw": ("YES", "text"),
        "published_iso": ("YES", "text"),
        "position": ("YES", "int2"),
        "query": ("YES", "text"),
        "serp_cache_key": ("YES", "text"),
        "metadata": ("NO", "jsonb"),
        "raw_key": ("NO", "text"),
        "collected_at": ("NO", "timestamptz"),
    }


def test_raw_items_defaults(ctx):
    conn, analysis, brand = ctx
    item_id = _new_raw_item(conn, analysis, brand)
    row = conn.execute(
        text("SELECT metadata, collected_at IS NOT NULL AS stamped FROM raw_items WHERE id = :i"),
        {"i": item_id},
    ).one()
    assert isinstance(item_id, uuid.UUID)
    assert row.metadata == {} and row.stamped


def test_raw_items_indexes_exist(migrated):
    with migrated.connect() as c:
        defs = {
            r[0]: r[1]
            for r in _rows(
                c,
                "SELECT indexname, indexdef FROM pg_indexes WHERE tablename = 'raw_items'",
            )
        }
    assert "UNIQUE" in defs["uq_raw_items_identity"]
    assert "(analysis_id, brand_id, purpose, raw_key)" in defs["uq_raw_items_identity"]
    assert '(analysis_id, brand_id, "window")' in defs["ix_raw_items_analysis_brand_window"]
    assert "(analysis_id, source_type)" in defs["ix_raw_items_analysis_source_type"]
    assert "(serp_cache_key)" in defs["ix_raw_items_serp_cache_key"]
    assert "pk_raw_items" in defs


def test_raw_items_identity_is_unique_per_analysis_brand_purpose(ctx):
    conn, analysis, brand = ctx
    _new_raw_item(conn, analysis, brand)
    with pytest.raises(IntegrityError), conn.begin_nested():
        _new_raw_item(conn, analysis, brand)
    # same key is fine for another brand, another analysis, or another purpose
    _new_raw_item(conn, analysis, _new_brand(conn, "Apple"))
    _new_raw_item(conn, _new_analysis(conn, brand), brand)
    _new_raw_item(conn, analysis, brand, purpose="investigation", window=None)


def test_raw_items_foreign_keys(ctx):
    conn, analysis, brand = ctx
    with pytest.raises(IntegrityError), conn.begin_nested():
        _new_raw_item(conn, uuid.uuid4(), brand)
    with pytest.raises(IntegrityError), conn.begin_nested():
        _new_raw_item(conn, analysis, uuid.uuid4())


def test_deleting_analysis_cascades_to_raw_items_but_not_brand(ctx):
    conn, analysis, brand = ctx
    _new_raw_item(conn, analysis, brand)
    conn.execute(text("DELETE FROM analyses WHERE id = :a"), {"a": analysis})
    assert _rows(conn, "SELECT count(*) FROM raw_items") == [(0,)]
    assert _rows(conn, "SELECT count(*) FROM brands WHERE id = :b", b=brand) == [(1,)]


def test_brand_with_raw_items_cannot_be_deleted(ctx):
    conn, analysis, brand = ctx
    _new_raw_item(conn, analysis, brand)
    with pytest.raises(IntegrityError), conn.begin_nested():
        conn.execute(text("DELETE FROM brands WHERE id = :b"), {"b": brand})


@pytest.mark.parametrize("engine", ["google_trends", "bing", ""])
def test_raw_items_reject_non_content_engines(ctx, engine):
    conn, analysis, brand = ctx
    with pytest.raises(IntegrityError), conn.begin_nested():
        _new_raw_item(conn, analysis, brand, engine=engine)


@pytest.mark.parametrize("engine", ["google", "google_news", "google_forums", "youtube"])
def test_raw_items_accept_content_engines(ctx, engine):
    conn, analysis, brand = ctx
    _new_raw_item(conn, analysis, brand, engine=engine)


@pytest.mark.parametrize("field", ["title", "url"])
@pytest.mark.parametrize("value", ["", "   ", "\n\t"])
def test_raw_items_reject_blank_title_and_url(ctx, field, value):
    conn, analysis, brand = ctx
    with pytest.raises(IntegrityError), conn.begin_nested():
        _new_raw_item(conn, analysis, brand, **{field: value})


@pytest.mark.parametrize("position", [0, -1])
def test_raw_items_reject_non_positive_position(ctx, position):
    conn, analysis, brand = ctx
    with pytest.raises(IntegrityError), conn.begin_nested():
        _new_raw_item(conn, analysis, brand, position=position)


@pytest.mark.parametrize("raw_key", ["", "abc", "A" * 64, "g" * 64, "a" * 63, "a" * 65])
def test_raw_items_reject_malformed_raw_key(ctx, raw_key):
    conn, analysis, brand = ctx
    with pytest.raises(IntegrityError), conn.begin_nested():
        _new_raw_item(conn, analysis, brand, raw_key=raw_key)


@pytest.mark.parametrize(
    ("purpose", "window", "ok"),
    [
        ("collection", "current", True),
        ("collection", "baseline", True),
        ("collection", None, False),
        ("investigation", None, True),
        ("investigation", "current", False),
    ],
)
def test_raw_items_purpose_window_rule(ctx, purpose, window, ok):
    conn, analysis, brand = ctx
    if ok:
        _new_raw_item(conn, analysis, brand, purpose=purpose, window=window)
    else:
        with pytest.raises(IntegrityError), conn.begin_nested():
            _new_raw_item(conn, analysis, brand, purpose=purpose, window=window)


def test_raw_items_enum_columns_reject_unknown_values(ctx):
    conn, analysis, brand = ctx
    with pytest.raises(DataError), conn.begin_nested():
        _new_raw_item(conn, analysis, brand, source_type="podcast")
    with pytest.raises(DataError), conn.begin_nested():
        _new_raw_item(conn, analysis, brand, window="future")
    with pytest.raises(DataError), conn.begin_nested():
        _new_raw_item(conn, analysis, brand, purpose="other")


# ---------- Phase 3.2: content_items ----------

HASH_A, HASH_B, HASH_C = "a" * 64, "b" * 64, "c" * 64


def _new_content_item(conn, analysis_id, brand_id, **overrides) -> uuid.UUID:
    values = {
        "analysis_id": analysis_id,
        "brand_id": brand_id,
        "purpose": "collection",
        "window": "current",
        "source_type": "news",
        "engine": "google_news",
        "url": "https://news.example.test/a",
        "url_hash": HASH_A,
        "domain": "news.example.test",
        "title": "Galaxy S25 Ultra battery drain",
        "date_confidence": "unknown",
        "query": "samsung",
        "content_hash": HASH_B,
    } | overrides
    cols = ", ".join(f'"{k}"' for k in values)
    params = ", ".join(f":{k}" for k in values)
    return conn.execute(
        text(f"INSERT INTO content_items ({cols}) VALUES ({params}) RETURNING id"), values
    ).scalar_one()


def test_content_items_columns_match_database_md(migrated):
    with migrated.connect() as c:
        rows = _rows(
            c,
            """SELECT column_name, is_nullable, udt_name FROM information_schema.columns
               WHERE table_name = 'content_items'""",
        )
    assert {name: (null, udt) for name, null, udt in rows} == {
        "id": ("NO", "uuid"),
        "analysis_id": ("NO", "uuid"),
        "brand_id": ("NO", "uuid"),
        "purpose": ("NO", "content_purpose"),
        "window": ("YES", "window_kind"),
        "source_type": ("NO", "source_type"),
        "engine": ("NO", "text"),
        "url": ("NO", "text"),
        "url_hash": ("NO", "text"),
        "domain": ("NO", "text"),
        "title": ("NO", "text"),
        "snippet": ("YES", "text"),
        "author": ("YES", "text"),
        "published_at": ("YES", "timestamptz"),
        "date_confidence": ("NO", "date_confidence"),
        "query": ("NO", "text"),
        "metadata": ("NO", "jsonb"),
        "content_hash": ("NO", "text"),
        "dup_group": ("YES", "text"),
        "serp_cache_key": ("YES", "text"),
        "collected_at": ("NO", "timestamptz"),
    }


def test_content_items_defaults(ctx):
    conn, analysis, brand = ctx
    item_id = _new_content_item(conn, analysis, brand)
    row = conn.execute(
        text("SELECT metadata, collected_at IS NOT NULL AS stamped FROM content_items WHERE id=:i"),
        {"i": item_id},
    ).one()
    assert isinstance(item_id, uuid.UUID) and row.metadata == {} and row.stamped


def test_content_items_indexes_exist(migrated):
    with migrated.connect() as c:
        defs = {
            r[0]: r[1]
            for r in _rows(
                c, "SELECT indexname, indexdef FROM pg_indexes WHERE tablename = 'content_items'"
            )
        }
    unique = defs["uq_content_items_identity"]
    assert "UNIQUE" in unique and "(analysis_id, brand_id, content_hash)" in unique
    assert '(analysis_id, brand_id, "window")' in defs["ix_content_items_analysis_brand_window"]
    assert "(analysis_id, source_type)" in defs["ix_content_items_analysis_source_type"]
    assert "(content_hash)" in defs["ix_content_items_content_hash"]
    assert "(analysis_id, brand_id, url_hash)" in defs["ix_content_items_analysis_brand_url_hash"]
    assert "(analysis_id, dup_group)" in defs["ix_content_items_analysis_dup_group"]
    assert "pk_content_items" in defs


def test_content_hash_is_unique_per_analysis_and_brand(ctx):
    conn, analysis, brand = ctx
    _new_content_item(conn, analysis, brand)
    with pytest.raises(IntegrityError), conn.begin_nested():
        _new_content_item(conn, analysis, brand, url="https://other.example.test/x")
    _new_content_item(conn, analysis, _new_brand(conn, "Apple"))  # other brand
    _new_content_item(conn, _new_analysis(conn, brand), brand)  # other analysis
    _new_content_item(conn, analysis, brand, content_hash=HASH_C)  # other text


def test_content_items_foreign_keys_and_cascade(ctx):
    conn, analysis, brand = ctx
    with pytest.raises(IntegrityError), conn.begin_nested():
        _new_content_item(conn, uuid.uuid4(), brand)
    with pytest.raises(IntegrityError), conn.begin_nested():
        _new_content_item(conn, analysis, uuid.uuid4())
    _new_content_item(conn, analysis, brand)
    with pytest.raises(IntegrityError), conn.begin_nested():
        conn.execute(text("DELETE FROM brands WHERE id = :b"), {"b": brand})
    conn.execute(text("DELETE FROM analyses WHERE id = :a"), {"a": analysis})
    assert _rows(conn, "SELECT count(*) FROM content_items") == [(0,)]
    assert _rows(conn, "SELECT count(*) FROM brands WHERE id = :b", b=brand) == [(1,)]


@pytest.mark.parametrize("engine", ["google_trends", "bing", ""])
def test_content_items_reject_non_content_engines(ctx, engine):
    conn, analysis, brand = ctx
    with pytest.raises(IntegrityError), conn.begin_nested():
        _new_content_item(conn, analysis, brand, engine=engine)


@pytest.mark.parametrize("field", ["title", "url", "domain"])
@pytest.mark.parametrize("value", ["", "   ", "\n\t"])
def test_content_items_reject_blank_text(ctx, field, value):
    conn, analysis, brand = ctx
    with pytest.raises(IntegrityError), conn.begin_nested():
        _new_content_item(conn, analysis, brand, **{field: value})


@pytest.mark.parametrize("field", ["url_hash", "content_hash", "dup_group"])
@pytest.mark.parametrize("value", ["", "abc", "A" * 64, "g" * 64, "a" * 63, "a" * 65])
def test_content_items_reject_malformed_hashes(ctx, field, value):
    conn, analysis, brand = ctx
    with pytest.raises(IntegrityError), conn.begin_nested():
        _new_content_item(conn, analysis, brand, **{field: value})


def test_dup_group_may_be_null_or_a_sha256(ctx):
    conn, analysis, brand = ctx
    _new_content_item(conn, analysis, brand, dup_group=None)
    _new_content_item(conn, analysis, brand, content_hash=HASH_C, dup_group=HASH_A)


@pytest.mark.parametrize(
    ("confidence", "published_at", "ok"),
    [
        ("unknown", None, True),
        ("exact", "2026-07-30T07:00:00Z", True),
        ("approximate", "2026-07-20T12:00:00Z", True),
        ("unknown", "2026-07-30T07:00:00Z", False),
        ("exact", None, False),
        ("approximate", None, False),
    ],
)
def test_content_items_date_exists_exactly_when_confidence_is_not_unknown(
    ctx, confidence, published_at, ok
):
    conn, analysis, brand = ctx
    kwargs = {"date_confidence": confidence, "published_at": published_at}
    if ok:
        _new_content_item(conn, analysis, brand, **kwargs)
    else:
        with pytest.raises(IntegrityError), conn.begin_nested():
            _new_content_item(conn, analysis, brand, **kwargs)


@pytest.mark.parametrize(
    ("purpose", "window", "ok"),
    [
        ("collection", "current", True),
        ("collection", "baseline", True),
        ("collection", None, True),  # dated outside both windows: kept, counts nowhere
        ("investigation", None, True),
        ("investigation", "current", False),
    ],
)
def test_content_items_window_rule(ctx, purpose, window, ok):
    conn, analysis, brand = ctx
    if ok:
        _new_content_item(conn, analysis, brand, purpose=purpose, window=window)
    else:
        with pytest.raises(IntegrityError), conn.begin_nested():
            _new_content_item(conn, analysis, brand, purpose=purpose, window=window)


def test_content_items_enum_columns_reject_unknown_values(ctx):
    conn, analysis, brand = ctx
    with pytest.raises(DataError), conn.begin_nested():
        _new_content_item(conn, analysis, brand, date_confidence="maybe")
    with pytest.raises(DataError), conn.begin_nested():
        _new_content_item(conn, analysis, brand, source_type="podcast")
    with pytest.raises(DataError), conn.begin_nested():
        _new_content_item(conn, analysis, brand, window="future")


# ---------- Phase 4.2: content_analysis / item_aspects ----------

VERSION = "m|lex-1|clauses-1|relevance-1|consumer_electronics"


def _new_analysis_row(conn, content_id, **overrides):
    values = {
        "content_id": content_id,
        "content_hash": HASH_B,
        "sentiment": "negative",
        "sentiment_score": -0.5,
        "negative_prob": 0.7,
        "is_about_brand": True,
        "model": "m",
        "analyzer_version": VERSION,
    } | overrides
    cols = ", ".join(f'"{k}"' for k in values)
    params = ", ".join(f":{k}" for k in values)
    conn.execute(text(f"INSERT INTO content_analysis ({cols}) VALUES ({params})"), values)


def _new_aspect_row(conn, content_id, **overrides):
    values = {
        "content_id": content_id,
        "aspect": "battery",
        "clause": "battery life is terrible",
        "sentiment": "negative",
        "negative_prob": 0.9,
        "score": -0.8,
    } | overrides
    cols = ", ".join(f'"{k}"' for k in values)
    params = ", ".join(f":{k}" for k in values)
    conn.execute(text(f"INSERT INTO item_aspects ({cols}) VALUES ({params})"), values)


@pytest.fixture
def item(ctx):
    conn, analysis, brand = ctx
    return conn, _new_content_item(conn, analysis, brand), analysis


def test_content_analysis_columns_match_database_md(migrated):
    with migrated.connect() as c:
        rows = _rows(
            c,
            """SELECT column_name, is_nullable, udt_name FROM information_schema.columns
               WHERE table_name = 'content_analysis'""",
        )
    assert {name: (null, udt) for name, null, udt in rows} == {
        "content_id": ("NO", "uuid"),
        "content_hash": ("NO", "text"),
        "sentiment": ("NO", "sentiment"),
        "sentiment_score": ("NO", "float4"),
        "negative_prob": ("NO", "float4"),
        "is_about_brand": ("NO", "bool"),
        "matched_terms": ("NO", "_text"),
        "topics": ("NO", "_text"),
        "keywords": ("NO", "_text"),
        "model": ("NO", "text"),
        "analyzer_version": ("NO", "text"),
        "analyzed_at": ("NO", "timestamptz"),
    }


def test_item_aspects_columns_match_database_md(migrated):
    with migrated.connect() as c:
        rows = _rows(
            c,
            """SELECT column_name, is_nullable, udt_name FROM information_schema.columns
               WHERE table_name = 'item_aspects'""",
        )
    assert {name: (null, udt) for name, null, udt in rows} == {
        "content_id": ("NO", "uuid"),
        "aspect": ("NO", "text"),
        "clause": ("NO", "text"),
        "sentiment": ("NO", "sentiment"),
        "negative_prob": ("NO", "float4"),
        "score": ("NO", "float4"),
    }


def test_nlp_indexes_and_primary_keys(migrated):
    with migrated.connect() as c:
        defs = {
            r[0]: r[1]
            for r in _rows(
                c,
                "SELECT indexname, indexdef FROM pg_indexes "
                "WHERE tablename IN ('content_analysis', 'item_aspects')",
            )
        }
    reuse = defs["ix_content_analysis_content_hash_analyzer_version"]
    assert "(content_hash, analyzer_version)" in reuse and "UNIQUE" not in reuse
    assert "(aspect, sentiment)" in defs["ix_item_aspects_aspect_sentiment"]
    assert "pk_content_analysis" in defs and "(content_id)" in defs["pk_content_analysis"]
    assert "(content_id, aspect)" in defs["pk_item_aspects"]


def test_content_analysis_defaults(item):
    conn, content_id, _ = item
    _new_analysis_row(conn, content_id)
    row = conn.execute(
        text(
            "SELECT matched_terms, topics, keywords, analyzed_at IS NOT NULL AS stamped "
            "FROM content_analysis WHERE content_id = :c"
        ),
        {"c": content_id},
    ).one()
    assert (row.matched_terms, row.topics, row.keywords, row.stamped) == ([], [], [], True)


def test_content_analysis_is_one_row_per_item(item):
    conn, content_id, _ = item
    _new_analysis_row(conn, content_id)
    with pytest.raises(IntegrityError), conn.begin_nested():
        _new_analysis_row(conn, content_id, analyzer_version="other")


def test_same_hash_and_version_may_exist_for_several_items(ctx):
    conn, analysis, brand = ctx
    first = _new_content_item(conn, analysis, brand)
    second = _new_content_item(conn, _new_analysis(conn, brand), brand)  # same text, other analysis
    _new_analysis_row(conn, first)
    _new_analysis_row(conn, second)  # the reuse index is not unique


def test_item_aspects_one_clause_per_aspect_per_item(item):
    conn, content_id, _ = item
    _new_aspect_row(conn, content_id)
    with pytest.raises(IntegrityError), conn.begin_nested():
        _new_aspect_row(conn, content_id, clause="another battery clause")
    _new_aspect_row(conn, content_id, aspect="camera")


@pytest.mark.parametrize(
    "overrides",
    [
        {"sentiment_score": 1.01},
        {"sentiment_score": -1.01},
        {"negative_prob": 1.01},
        {"negative_prob": -0.01},
        {"content_hash": "A" * 64},
        {"content_hash": "a" * 63},
        {"model": " \t"},
        {"analyzer_version": ""},
    ],
)
def test_content_analysis_check_constraints(item, overrides):
    conn, content_id, _ = item
    with pytest.raises(IntegrityError), conn.begin_nested():
        _new_analysis_row(conn, content_id, **overrides)


@pytest.mark.parametrize(
    "ok", [{"sentiment_score": 1}, {"sentiment_score": -1}, {"negative_prob": 0}]
)
def test_content_analysis_range_edges_are_allowed(item, ok):
    conn, content_id, _ = item
    _new_analysis_row(conn, content_id, **ok)


@pytest.mark.parametrize(
    "overrides",
    [
        {"aspect": " "},
        {"clause": "\n"},
        {"negative_prob": 1.5},
        {"negative_prob": -0.5},
        {"score": 1.5},
        {"score": -1.5},
    ],
)
def test_item_aspects_check_constraints(item, overrides):
    conn, content_id, _ = item
    with pytest.raises(IntegrityError), conn.begin_nested():
        _new_aspect_row(conn, content_id, **overrides)


def test_nlp_rows_need_an_existing_content_item(ctx):
    conn, _, _ = ctx
    with pytest.raises(IntegrityError), conn.begin_nested():
        _new_analysis_row(conn, uuid.uuid4())
    with pytest.raises(IntegrityError), conn.begin_nested():
        _new_aspect_row(conn, uuid.uuid4())


def test_nlp_enum_columns_reject_unknown_values(item):
    conn, content_id, _ = item
    with pytest.raises(DataError), conn.begin_nested():
        _new_analysis_row(conn, content_id, sentiment="mixed")
    with pytest.raises(DataError), conn.begin_nested():
        _new_aspect_row(conn, content_id, sentiment="mixed")


def test_deleting_an_analysis_removes_its_nlp_rows(item):
    conn, content_id, analysis = item
    _new_analysis_row(conn, content_id)
    _new_aspect_row(conn, content_id)
    conn.execute(text("DELETE FROM analyses WHERE id = :a"), {"a": analysis})
    assert _rows(conn, "SELECT count(*) FROM content_items") == [(0,)]
    assert _rows(conn, "SELECT count(*) FROM content_analysis") == [(0,)]
    assert _rows(conn, "SELECT count(*) FROM item_aspects") == [(0,)]


def test_downgrade_0005_keeps_the_sentiment_enum_and_content_items():
    with blank_database() as url:
        cfg = _cfg(url)
        command.upgrade(cfg, "head")
        command.downgrade(cfg, "0004")
        engine = create_engine(url)
        with engine.connect() as c:
            labels = _rows(
                c,
                "SELECT enumlabel FROM pg_enum e JOIN pg_type t ON t.oid = e.enumtypid "
                "WHERE t.typname = 'sentiment' ORDER BY enumsortorder",
            )
        assert labels == [("positive",), ("neutral",), ("negative",)]
        assert "content_items" in _tables(engine)
        engine.dispose()
