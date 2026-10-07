"""ContentItemRepository against a real PostgreSQL (skipped without TEST_DATABASE_URL).

Items are produced by the real processor from the synthetic fixtures. No SerpApi calls.
"""

import uuid
from datetime import UTC, date, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.db.repositories.content_item import ContentItemRepository
from app.schemas.domain import ContentPurpose, DateConfidence, SourceType, WindowKind
from app.schemas.processing import ContentItem, StoredContentItem
from app.schemas.serp import SerpEngine, WindowSet
from app.services.processing.processor import process_raw_items

WINDOWS = WindowSet(
    as_of_date=date(2026, 8, 10),
    period_days=30,
    current_start=date(2026, 7, 12),
    current_end=date(2026, 8, 10),
    baseline_start=date(2026, 6, 12),
    baseline_end=date(2026, 7, 11),
)
ENGINES = [SerpEngine.google, SerpEngine.google_news, SerpEngine.google_forums, SerpEngine.youtube]


@pytest.fixture
def repo(migrated_engine):
    return ContentItemRepository(migrated_engine)


@pytest.fixture
def brand(new_brand):
    return new_brand()


@pytest.fixture
def analysis(new_analysis, brand):
    return new_analysis(brand)


@pytest.fixture
def items(stored_raw, fixture_raw_items, analysis, brand) -> list[ContentItem]:
    raws = [
        stored_raw(item, analysis_id=analysis, brand_id=brand)
        for engine in ENGINES
        for item in fixture_raw_items(engine)
    ]
    return process_raw_items(raws, windows=WINDOWS).items


def test_every_processed_fixture_item_round_trips_losslessly(repo, analysis, brand, items):
    result = repo.add_many(analysis, brand, items)
    assert (result.inserted, result.duplicates) == (len(items), 0)
    assert len(result.inserted_ids) == len(items) == 14

    stored = repo.list_for_analysis(analysis)
    assert len(stored) == len(items) and all(isinstance(s, StoredContentItem) for s in stored)
    by_hash = {s.content_hash: s for s in stored}
    for item in items:
        row = by_hash[item.content_hash]
        for field in ContentItem.model_fields:
            assert getattr(row, field) == getattr(item, field), field
        assert row.analysis_id == analysis and row.brand_id == brand


def test_dates_confidence_and_windows_survive_storage(repo, analysis, brand, items):
    repo.add_many(analysis, brand, items)
    stored = repo.list_for_analysis(analysis)
    assert sum(s.date_confidence is DateConfidence.exact for s in stored) == 6
    assert sum(s.date_confidence is DateConfidence.approximate for s in stored) == 4
    assert all(
        (s.published_at is None) == (s.date_confidence is DateConfidence.unknown) for s in stored
    )
    assert all(s.published_at is None or s.published_at.tzinfo is not None for s in stored)
    assert repo.count(analysis, window=WindowKind.baseline) == 1
    assert repo.count(analysis, window=WindowKind.current) == 13


def test_get_by_id_and_add_single(repo, analysis, brand, items):
    stored, created = repo.add(analysis, brand, items[0])
    assert created and repo.get(stored.id) == stored
    assert repo.get(uuid.uuid4()) is None
    again, created_again = repo.add(analysis, brand, items[0])
    assert not created_again and again.id == stored.id


def test_repeat_batches_are_skipped_not_updated(repo, analysis, brand, items):
    repo.add_many(analysis, brand, items)
    before = {s.id: s for s in repo.list_for_analysis(analysis)}
    again = repo.add_many(analysis, brand, items)
    assert (again.inserted, again.duplicates, again.inserted_ids) == (0, len(items), [])
    assert {s.id: s for s in repo.list_for_analysis(analysis)} == before


def test_identical_items_inside_one_batch_are_stored_once(repo, analysis, brand, items):
    result = repo.add_many(analysis, brand, [items[0], items[0], items[0]])
    assert (result.inserted, result.duplicates) == (1, 2)


def test_empty_batch_is_a_no_op(repo, analysis, brand):
    result = repo.add_many(analysis, brand, [])
    assert (result.inserted, result.duplicates) == (0, 0)
    assert repo.count(analysis) == 0


def test_same_item_may_exist_for_another_brand_or_analysis(
    repo, new_brand, new_analysis, analysis, brand, items
):
    repo.add_many(analysis, brand, items[:1])
    assert repo.add(analysis, new_brand("Apple"), items[0])[1]
    assert repo.add(new_analysis(brand), brand, items[0])[1]
    assert not repo.add(analysis, brand, items[0])[1]


def test_filters_count_and_order(repo, new_brand, analysis, brand, items):
    apple = new_brand("Apple")
    repo.add_many(analysis, brand, items)
    repo.add_many(analysis, apple, items[:3])
    assert repo.count(analysis) == len(items) + 3
    assert repo.count(analysis, brand_id=apple) == 3
    assert repo.count(analysis, brand_id=brand, source_type=SourceType.news) == 5
    assert repo.count(analysis, brand_id=brand, purpose=ContentPurpose.investigation) == 0
    rows = repo.list_for_analysis(analysis, brand_id=brand, source_type=SourceType.youtube)
    assert {r.source_type for r in rows} == {SourceType.youtube} and len(rows) == 3
    everything = repo.list_for_analysis(analysis)
    assert everything == repo.list_for_analysis(analysis)
    assert repo.list_for_analysis(analysis, limit=4) == everything[:4]
    assert repo.list_for_analysis(analysis, limit=4, offset=4) == everything[4:8]
    assert repo.count(uuid.uuid4()) == 0 and repo.list_for_analysis(uuid.uuid4()) == []


def test_hash_checks(repo, new_brand, analysis, brand, items):
    stored, absent = items[:5], items[5:]
    repo.add_many(analysis, brand, stored)
    content = [i.content_hash for i in items]
    urls = [i.url_hash for i in items]
    assert repo.existing_content_hashes(analysis, brand, content) == {
        i.content_hash for i in stored
    }
    assert repo.existing_url_hashes(analysis, brand, urls) == {i.url_hash for i in stored}
    assert not repo.existing_content_hashes(analysis, brand, [i.content_hash for i in absent])
    assert repo.existing_content_hashes(analysis, brand, []) == set()
    assert repo.existing_url_hashes(analysis, brand, []) == set()
    assert not repo.existing_content_hashes(analysis, new_brand("Apple"), content)
    known_content, known_urls = repo.stored_hashes(analysis, brand)
    assert known_content == {i.content_hash for i in stored}
    assert known_urls == {i.url_hash for i in stored}


def test_count_dup_groups_counts_independent_sources(repo, analysis, brand, items):
    a = items[0]
    b = a.model_copy(update={"content_hash": "d" * 64, "url_hash": "e" * 64})  # same dup_group
    c = items[1]
    repo.add_many(analysis, brand, [a, b, c])
    assert repo.count(analysis) == 3
    assert repo.count_dup_groups(analysis) == 2
    assert repo.count_dup_groups(analysis, brand_id=brand) == 2


def test_investigation_item_without_window_is_stored(repo, analysis, brand, items):
    investigation = items[0].model_copy(
        update={"purpose": ContentPurpose.investigation, "window": None}
    )
    stored, created = repo.add(analysis, brand, investigation)
    assert created and stored.purpose is ContentPurpose.investigation and stored.window is None


def test_a_batch_is_all_or_nothing(repo, analysis, brand, items):
    bad = ContentItem.model_construct(**{**items[1].model_dump(), "domain": "   "})
    with pytest.raises(IntegrityError):
        repo.add_many(analysis, brand, [items[0], bad])
    assert repo.count(analysis) == 0


def test_unknown_analysis_is_rejected_by_foreign_key(repo, brand, items):
    with pytest.raises(IntegrityError):
        repo.add(uuid.uuid4(), brand, items[0])


def test_deleting_the_analysis_removes_its_content_items(
    migrated_engine, repo, new_analysis, analysis, brand, items
):
    other = new_analysis(brand)
    repo.add_many(analysis, brand, items)
    repo.add_many(other, brand, items)
    with migrated_engine.begin() as conn:
        conn.execute(text("DELETE FROM analyses WHERE id = :a"), {"a": analysis})
    assert repo.count(analysis) == 0 and repo.count(other) == len(items)


def test_published_at_is_returned_in_utc(repo, analysis, brand, items):
    news = next(i for i in items if i.source_type is SourceType.news)
    stored, _ = repo.add(analysis, brand, news)
    assert stored.published_at == news.published_at
    assert stored.published_at.astimezone(UTC) == news.published_at.astimezone(UTC)
    assert isinstance(stored.collected_at, datetime)
