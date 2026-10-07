"""DB-backed SerpApi stores against a real PostgreSQL (skipped without TEST_DATABASE_URL).

Runs the same service-level behaviours as the in-memory unit tests, through
`SerpCacheRepository` / `SerpUsageRepository` + Alembic head.
"""

import os
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from alembic import command
from app.db.repositories.serp_cache import SerpCacheRepository
from app.db.repositories.serp_usage import SerpUsageRepository
from app.db.session import normalize_url
from app.schemas.serp import (
    CacheEntry,
    QuerySpec,
    SerpEngine,
    UsagePurpose,
    UsageRecord,
)
from app.services.serpapi.cache import ResponseCache
from app.services.serpapi.usage import MonthlyQuota

ADMIN_URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not ADMIN_URL, reason="TEST_DATABASE_URL not set (needs a PostgreSQL server)"
)

ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"
NOW = datetime(2026, 10, 6, 12, 0, tzinfo=UTC)
SPEC = QuerySpec(engine=SerpEngine.google, params={"q": "Samsung S25", "hl": "en"})
HIT = {"organic_results": [{"title": "t", "link": "https://a.example.test"}]}


@contextmanager
def blank_database():
    name = f"bp_serptest_{uuid.uuid4().hex[:12]}"
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
def engine():
    with blank_database() as url:
        cfg = Config(str(ALEMBIC_INI))
        cfg.attributes["url"] = url
        command.upgrade(cfg, "head")
        eng = create_engine(url)
        yield eng
        eng.dispose()


def entry(key="k1", *, expires_in=timedelta(hours=1), pinned=False):
    return CacheEntry(
        cache_key=key,
        engine="google",
        params={"q": "x"},
        response=HIT,
        http_status=200,
        fetched_at=NOW,
        expires_at=NOW + expires_in,
        pinned=pinned,
    )


def usage(label="acct", credits=1, at=NOW, **kw):
    return UsageRecord(
        cache_key="k",
        engine="google",
        cache_hit=credits == 0,
        credits=credits,
        purpose=UsagePurpose.analysis,
        account_label=label,
        created_at=at,
        **kw,
    )


def test_cache_round_trip_and_upsert(engine):
    repo = SerpCacheRepository(engine)
    assert repo.get("k1") is None
    repo.put(entry())
    got = repo.get("k1")
    assert got.response == HIT and got.params == {"q": "x"} and got.pinned is False
    assert got.expires_at == NOW + timedelta(hours=1)
    repo.put(entry(expires_in=timedelta(hours=9)))  # refresh replaces the row
    assert repo.get("k1").expires_at == NOW + timedelta(hours=9)


def test_pin_and_purge_never_touch_pinned_rows(engine):
    repo = SerpCacheRepository(engine)
    repo.put(entry("old", expires_in=timedelta(hours=-1)))
    repo.put(entry("pinned", expires_in=timedelta(hours=-1), pinned=True))
    repo.put(entry("fresh"))
    assert repo.set_pinned("missing", True) is False
    assert repo.purge_expired(NOW) == 1
    assert repo.get("old") is None
    assert repo.get("pinned") is not None and repo.get("fresh") is not None
    repo.set_pinned("pinned", False)
    assert repo.purge_expired(NOW) == 1


def test_monthly_credits_respects_label_and_month_bounds(engine):
    repo = SerpUsageRepository(engine)
    repo.add(usage())
    repo.add(usage())
    repo.add(usage(credits=0))  # cache hit
    repo.add(usage(label="other"))
    repo.add(usage(at=datetime(2026, 9, 30, 23, 59, tzinfo=UTC)))
    repo.add(usage(at=datetime(2026, 11, 1, tzinfo=UTC)))
    start, end = datetime(2026, 10, 1, tzinfo=UTC), datetime(2026, 11, 1, tzinfo=UTC)
    assert repo.monthly_credits("acct", start, end) == 2
    assert repo.monthly_credits("nobody", start, end) == 0


def test_services_work_end_to_end_over_the_repositories(engine):
    cache = ResponseCache(SerpCacheRepository(engine), ttl_hours=720, clock=lambda: NOW)
    quota = MonthlyQuota(
        SerpUsageRepository(engine),
        account_label="acct",
        limit=250,
        reserve=20,
        allow_live=True,
        clock=lambda: NOW,
    )
    assert not cache.contains(SPEC)
    cache.store(SPEC, {**HIT, "api_key": "SECRET"})
    assert cache.contains(SPEC) and cache.pin(SPEC)
    with engine.connect() as c:
        stored = c.execute(text("SELECT response::text FROM serp_cache")).scalar_one()
    assert "SECRET" not in stored
    quota.record(
        cache_key="k",
        engine="google",
        cache_hit=False,
        credits=1,
        purpose=UsagePurpose.probe,
    )
    assert quota.snapshot().used == 1 and quota.snapshot().remaining == 249
