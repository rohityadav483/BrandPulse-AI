"""RawItemRepository against a real PostgreSQL (skipped without TEST_DATABASE_URL).

Items come from the synthetic SerpApi fixtures through the real parsers; nothing here calls
SerpApi. Covers create, retrieve, check, idempotency, atomicity and the cascade on delete.
"""

import json
import os
import uuid
from contextlib import contextmanager
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError

from alembic import command
from app.db.repositories.raw_item import RawItemRepository
from app.db.session import normalize_url
from app.schemas.domain import ContentPurpose, SourceType, WindowKind
from app.schemas.serp import (
    QuerySpec,
    RawItem,
    RawItemContext,
    SerpEngine,
    StoredRawItem,
)
from app.services.serpapi.cache import cache_key
from app.services.serpapi.parsers import parse_response

ADMIN_URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not ADMIN_URL, reason="TEST_DATABASE_URL not set (needs a PostgreSQL server)"
)

ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"
FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "serpapi"
CONTENT_FIXTURES = {
    SerpEngine.google: "google_web_samsung_s25_ultra.json",
    SerpEngine.google_news: "google_news_samsung_s25_ultra.json",
    SerpEngine.google_forums: "google_forums_samsung_s25_ultra.json",
    SerpEngine.youtube: "youtube_samsung_s25_ultra.json",
}
NOW = datetime(2026, 10, 7, 9, 0, tzinfo=UTC)


@contextmanager
def blank_database():
    name = f"bp_rawtest_{uuid.uuid4().hex[:12]}"
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


@pytest.fixture
def repo(engine):
    return RawItemRepository(engine)


def _brand(engine, name="Samsung") -> uuid.UUID:
    with engine.begin() as conn:
        return conn.execute(
            text(
                "INSERT INTO brands (name, normalized_name) VALUES (:n, :nn) RETURNING id"
            ),
            {"n": name, "nn": name.lower()},
        ).scalar_one()


def _analysis(engine, brand_id) -> uuid.UUID:
    with engine.begin() as conn:
        return conn.execute(
            text(
                "INSERT INTO analyses (brand_id, as_of_date, current_start, current_end, "
                "baseline_start, baseline_end) VALUES (:b, :a, :cs, :ce, :bs, :be) RETURNING id"
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


@pytest.fixture
def brand(engine):
    return _brand(engine)


@pytest.fixture
def analysis(engine, brand):
    return _analysis(engine, brand)


def ctx(analysis, brand, window=WindowKind.current, **kw) -> RawItemContext:
    return RawItemContext(analysis_id=analysis, brand_id=brand, window=window, **kw)


def fixture_items(engine_name: SerpEngine) -> list[RawItem]:
    param = "search_query" if engine_name is SerpEngine.youtube else "q"
    spec = QuerySpec(engine=engine_name, params={param: "Samsung Galaxy S25 Ultra"})
    response = json.loads(
        (FIXTURES / CONTENT_FIXTURES[engine_name]).read_text(encoding="utf-8")
    )
    parsed = parse_response(
        spec, response, cache_key=cache_key(spec.engine, spec.params)
    )
    return parsed.items


def all_fixture_items() -> list[RawItem]:
    return [item for name in CONTENT_FIXTURES for item in fixture_items(name)]


# ---------- create + retrieve ----------


def test_every_engine_fixture_round_trips_losslessly(repo, analysis, brand):
    items = all_fixture_items()
    result = repo.add_many(ctx(analysis, brand, collected_at=NOW), items)
    assert (result.inserted, result.duplicates, result.total) == (
        len(items),
        0,
        len(items),
    )
    assert len(result.inserted_ids) == len(items)

    stored = repo.list_for_analysis(analysis)
    assert len(stored) == len(items)
    assert all(isinstance(s, StoredRawItem) for s in stored)
    by_key = {s.raw_key: s for s in stored}
    for item in items:
        row = by_key[item.compute_raw_key()]
        for field in RawItem.model_fields:
            assert getattr(row, field) == getattr(item, field), field
        assert row.analysis_id == analysis and row.brand_id == brand
        assert row.purpose is ContentPurpose.collection
        assert row.window is WindowKind.current
        assert row.collected_at == NOW


def test_all_four_source_types_are_stored(repo, analysis, brand):
    repo.add_many(ctx(analysis, brand), all_fixture_items())
    types = {s.source_type for s in repo.list_for_analysis(analysis)}
    assert types == {
        SourceType.web,
        SourceType.news,
        SourceType.forum,
        SourceType.youtube,
    }
    for source in types:
        assert repo.count(analysis, source_type=source) > 0


def test_values_are_stored_verbatim_without_normalisation(repo, analysis, brand):
    item = RawItem(
        source_type=SourceType.web,
        engine=SerpEngine.google,
        title="  Mixed CASE title \n",
        url=" HTTPS://Example.TEST/Path?utm_source=x#frag ",
        snippet="",
        published_raw="3 weeks ago",
    )
    stored, created = repo.add(ctx(analysis, brand), item)
    assert created
    assert stored.title == item.title and stored.url == item.url
    assert stored.snippet == "" and stored.published_iso is None


def test_db_stamps_collected_at_when_context_has_none(repo, analysis, brand):
    stored, _ = repo.add(ctx(analysis, brand), fixture_items(SerpEngine.google)[0])
    assert stored.collected_at is not None and stored.collected_at.tzinfo is not None


def test_add_single_and_get_by_id(repo, analysis, brand):
    item = fixture_items(SerpEngine.google_news)[0]
    stored, created = repo.add(ctx(analysis, brand), item)
    assert created and isinstance(stored.id, uuid.UUID)
    assert repo.get(stored.id) == stored
    assert repo.get(uuid.uuid4()) is None


def test_json_metadata_round_trips(repo, analysis, brand):
    youtube = fixture_items(SerpEngine.youtube)[0]
    assert youtube.metadata  # views, length, ...
    stored, _ = repo.add(ctx(analysis, brand), youtube)
    assert stored.metadata == youtube.metadata


def test_empty_batch_is_a_no_op(repo, analysis, brand):
    result = repo.add_many(ctx(analysis, brand), [])
    assert (result.inserted, result.duplicates, result.inserted_ids) == (0, 0, [])
    assert repo.count(analysis) == 0


def test_empty_serp_response_persists_nothing(repo, analysis, brand):
    spec = QuerySpec(engine=SerpEngine.google, params={"q": "nothing"})
    response = json.loads(
        (FIXTURES / "google_no_results.json").read_text(encoding="utf-8")
    )
    parsed = parse_response(spec, response)
    assert parsed.items == []
    assert repo.add_many(ctx(analysis, brand), parsed.items).inserted == 0


def test_trends_response_yields_no_raw_items(repo, analysis, brand):
    spec = QuerySpec(engine=SerpEngine.google_trends, params={"q": "Samsung,Apple"})
    response = json.loads(
        (FIXTURES / "google_trends_samsung_apple_oneplus.json").read_text(
            encoding="utf-8"
        )
    )
    parsed = parse_response(spec, response)
    assert parsed.items == [] and parsed.trends is not None


# ---------- idempotency (exact repeats only; no dedupe logic) ----------


def test_re_persisting_the_same_response_is_a_no_op(repo, analysis, brand):
    items = fixture_items(SerpEngine.google_news)
    first = repo.add_many(ctx(analysis, brand), items)
    again = repo.add_many(ctx(analysis, brand), items)
    assert first.inserted == len(items)
    assert (again.inserted, again.duplicates, again.inserted_ids) == (0, len(items), [])
    assert repo.count(analysis) == len(items)


def test_partial_overlap_inserts_only_the_new_items(repo, analysis, brand):
    items = fixture_items(SerpEngine.google_news)
    repo.add_many(ctx(analysis, brand), items[:2])
    result = repo.add_many(ctx(analysis, brand), items)
    assert (result.inserted, result.duplicates) == (len(items) - 2, 2)
    assert repo.count(analysis) == len(items)


def test_identical_items_inside_one_batch_are_stored_once(repo, analysis, brand):
    item = fixture_items(SerpEngine.google)[0]
    result = repo.add_many(ctx(analysis, brand), [item, item, item])
    assert (result.inserted, result.duplicates) == (1, 2)
    assert repo.count(analysis) == 1


def test_add_reports_repeat_and_returns_the_original_row(repo, analysis, brand):
    item = fixture_items(SerpEngine.google)[0]
    first, created_first = repo.add(ctx(analysis, brand), item)
    second, created_second = repo.add(ctx(analysis, brand), item)
    assert created_first and not created_second
    assert second.id == first.id


def test_same_article_found_by_two_queries_stays_two_raw_rows(repo, analysis, brand):
    """Merging near-duplicates is Phase 3.2: raw storage keeps every occurrence."""
    item = fixture_items(SerpEngine.google)[0]
    other_query = item.model_copy(
        update={"query": "s25 ultra battery", "serp_cache_key": "k2"}
    )
    result = repo.add_many(ctx(analysis, brand), [item, other_query])
    assert result.inserted == 2
    assert len({s.url for s in repo.list_for_analysis(analysis)}) == 1


def test_same_item_may_exist_in_other_analysis_brand_or_purpose(
    engine, repo, analysis, brand
):
    item = fixture_items(SerpEngine.google)[0]
    repo.add(ctx(analysis, brand), item)
    other_analysis = _analysis(engine, brand)
    other_brand = _brand(engine, "Apple")
    assert repo.add(ctx(other_analysis, brand), item)[1]
    assert repo.add(ctx(analysis, other_brand), item)[1]
    investigation = RawItemContext(
        analysis_id=analysis, brand_id=brand, purpose=ContentPurpose.investigation
    )
    assert repo.add(investigation, item)[1]
    assert not repo.add(ctx(analysis, brand), item)[1]


def test_windows_do_not_collide_when_cache_keys_differ(repo, analysis, brand):
    base = fixture_items(SerpEngine.google)[0]
    baseline_item = base.model_copy(update={"serp_cache_key": "baseline-call"})
    repo.add(ctx(analysis, brand, WindowKind.current), base)
    repo.add(ctx(analysis, brand, WindowKind.baseline), baseline_item)
    assert repo.count(analysis, window=WindowKind.current) == 1
    assert repo.count(analysis, window=WindowKind.baseline) == 1


# ---------- list / count filters ----------


def test_list_and_count_filters(engine, repo, analysis, brand):
    apple = _brand(engine, "Apple")
    web, news = fixture_items(SerpEngine.google), fixture_items(SerpEngine.google_news)
    repo.add_many(ctx(analysis, brand, WindowKind.current), web)
    repo.add_many(ctx(analysis, brand, WindowKind.baseline), news)
    repo.add_many(ctx(analysis, apple, WindowKind.current), web)
    repo.add_many(
        RawItemContext(
            analysis_id=analysis, brand_id=brand, purpose=ContentPurpose.investigation
        ),
        web[:1],
    )

    assert repo.count(analysis) == 2 * len(web) + len(news) + 1
    assert repo.count(analysis, brand_id=apple) == len(web)
    assert repo.count(analysis, brand_id=brand, purpose=ContentPurpose.collection) == (
        len(web) + len(news)
    )
    assert repo.count(analysis, purpose=ContentPurpose.investigation) == 1
    assert repo.count(analysis, brand_id=brand, window=WindowKind.baseline) == len(news)
    assert repo.count(analysis, source_type=SourceType.news) == len(news)

    rows = repo.list_for_analysis(analysis, brand_id=brand, window=WindowKind.baseline)
    assert {r.source_type for r in rows} == {SourceType.news}
    assert len(rows) == len(news)
    assert repo.count(uuid.uuid4()) == 0 and repo.list_for_analysis(uuid.uuid4()) == []


def test_list_order_is_stable_and_paged(repo, analysis, brand):
    items = fixture_items(SerpEngine.google_news)
    repo.add_many(ctx(analysis, brand, collected_at=NOW), items)
    everything = repo.list_for_analysis(analysis)
    assert everything == repo.list_for_analysis(analysis)
    positions = [r.position for r in everything]
    assert positions == sorted(positions, key=lambda p: (p is None, p))
    assert repo.list_for_analysis(analysis, limit=2) == everything[:2]
    assert repo.list_for_analysis(analysis, limit=2, offset=2) == everything[2:4]
    assert repo.list_for_analysis(analysis, offset=len(everything)) == []


# ---------- check ----------


def test_exists_and_existing_keys(engine, repo, analysis, brand):
    items = fixture_items(SerpEngine.google_news)
    stored, absent = items[:2], items[2:]
    repo.add_many(ctx(analysis, brand), stored)
    context = ctx(analysis, brand)
    assert all(repo.exists(context, item) for item in stored)
    assert not any(repo.exists(context, item) for item in absent)

    keys = [i.compute_raw_key() for i in items]
    found = repo.existing_keys(analysis, brand, ContentPurpose.collection, keys)
    assert found == {i.compute_raw_key() for i in stored}
    assert repo.existing_keys(analysis, brand, ContentPurpose.collection, []) == set()


def test_exists_is_scoped_to_analysis_brand_and_purpose(engine, repo, analysis, brand):
    item = fixture_items(SerpEngine.google)[0]
    repo.add(ctx(analysis, brand), item)
    assert repo.exists(ctx(analysis, brand), item)
    assert not repo.exists(ctx(_analysis(engine, brand), brand), item)
    assert not repo.exists(ctx(analysis, _brand(engine, "Apple")), item)
    investigation = RawItemContext(
        analysis_id=analysis, brand_id=brand, purpose=ContentPurpose.investigation
    )
    assert not repo.exists(investigation, item)


# ---------- atomicity + cascade ----------


def test_a_batch_is_all_or_nothing(repo, analysis, brand):
    good = fixture_items(SerpEngine.google)[0]
    bad = (
        RawItem.model_construct(  # bypasses validation to reach the DB check constraint
            **{
                **good.model_dump(),
                "title": "bad",
                "position": 0,
                "url": "https://bad.example.test",
            }
        )
    )
    with pytest.raises(IntegrityError):
        repo.add_many(ctx(analysis, brand), [good, bad])
    assert repo.count(analysis) == 0


def test_unknown_analysis_is_rejected_by_foreign_key(repo, brand):
    with pytest.raises(IntegrityError):
        repo.add(ctx(uuid.uuid4(), brand), fixture_items(SerpEngine.google)[0])


def test_deleting_the_analysis_removes_its_raw_items(engine, repo, analysis, brand):
    other = _analysis(engine, brand)
    items = fixture_items(SerpEngine.google)
    repo.add_many(ctx(analysis, brand), items)
    repo.add_many(ctx(other, brand), items)
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM analyses WHERE id = :a"), {"a": analysis})
    assert repo.count(analysis) == 0
    assert repo.count(other) == len(items)
