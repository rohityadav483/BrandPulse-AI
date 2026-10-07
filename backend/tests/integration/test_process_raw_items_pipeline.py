"""raw_items -> content_items on a real PostgreSQL (skipped without TEST_DATABASE_URL).

Uses the Phase 3.1 repository to persist fixture RawItems, then the Phase 3.2 pipeline stage.
Nothing here calls SerpApi: the stage only reads rows that already exist.
"""

import ast
import inspect
from datetime import UTC, date, datetime

import pytest

from app.db.repositories.content_item import ContentItemRepository
from app.db.repositories.raw_item import RawItemRepository
from app.pipeline import process_raw_items as stage
from app.pipeline.process_raw_items import process_analysis_raw_items
from app.schemas.domain import ContentPurpose, DateConfidence, SourceType, WindowKind
from app.schemas.processing import DropReason
from app.schemas.serp import RawItem, RawItemContext, SerpEngine, WindowSet

WINDOWS = WindowSet(
    as_of_date=date(2026, 8, 10),
    period_days=30,
    current_start=date(2026, 7, 12),
    current_end=date(2026, 8, 10),
    baseline_start=date(2026, 6, 12),
    baseline_end=date(2026, 7, 11),
)
ENGINES = [
    SerpEngine.google,
    SerpEngine.google_news,
    SerpEngine.google_forums,
    SerpEngine.youtube,
]
COLLECTED = datetime(2026, 8, 10, 12, 0, tzinfo=UTC)


@pytest.fixture
def raw_repo(migrated_engine):
    return RawItemRepository(migrated_engine)


@pytest.fixture
def content_repo(migrated_engine):
    return ContentItemRepository(migrated_engine)


@pytest.fixture
def brand(new_brand):
    return new_brand()


@pytest.fixture
def analysis(new_analysis, brand):
    return new_analysis(brand)


@pytest.fixture
def load_fixtures(raw_repo, fixture_raw_items):
    """Persist all four fixtures as raw_items for (analysis, brand) in the given window."""

    def _load(analysis, brand, window=WindowKind.current):
        context = RawItemContext(
            analysis_id=analysis, brand_id=brand, window=window, collected_at=COLLECTED
        )
        for engine in ENGINES:
            raw_repo.add_many(context, fixture_raw_items(engine))

    return _load


def _raw(**fields) -> RawItem:
    values = {
        "source_type": SourceType.news,
        "engine": SerpEngine.google_news,
        "title": "Samsung confirms charging slowdown on Galaxy S25 Ultra",
        "url": "https://wire.example.test/charging",
        "snippet": "Samsung says a fix is coming.",
        "author": "Example Wire",
        "published_raw": "08/02/2026, 10:15 AM, +0000 UTC",
        "position": 1,
        "query": "samsung s25 ultra",
        "serp_cache_key": "k1",
    } | fields
    return RawItem(**values)


def test_fixtures_flow_from_raw_items_into_content_items(
    raw_repo, content_repo, analysis, brand, load_fixtures
):
    load_fixtures(analysis, brand)
    assert raw_repo.count(analysis) == 14

    result = process_analysis_raw_items(
        raw_repo, content_repo, analysis, windows=WINDOWS
    )
    assert (result.raw_read, result.kept, result.inserted, result.db_duplicates) == (
        14,
        14,
        14,
        0,
    )
    assert result.dropped == [] and result.stats.kept == 14
    assert (
        result.stats.date_exact,
        result.stats.date_approximate,
        result.stats.date_unknown,
    ) == (
        6,
        4,
        4,
    )
    assert content_repo.count(analysis) == 14
    assert content_repo.count(analysis, window=WindowKind.baseline) == 1
    assert content_repo.count(analysis, source_type=SourceType.news) == 5

    news = next(
        i
        for i in content_repo.list_for_analysis(analysis)
        if i.url.endswith("s25-ultra-battery-drain")
    )
    assert news.published_at == datetime(2026, 7, 30, 7, tzinfo=UTC)
    assert (
        news.date_confidence is DateConfidence.exact
        and news.window is WindowKind.current
    )
    assert news.domain == "news.example.test" and news.serp_cache_key


def test_raw_items_are_only_read_never_changed(
    raw_repo, content_repo, analysis, brand, load_fixtures
):
    load_fixtures(analysis, brand)
    before = raw_repo.list_for_analysis(analysis)
    process_analysis_raw_items(raw_repo, content_repo, analysis, windows=WINDOWS)
    assert raw_repo.list_for_analysis(analysis) == before


def test_rerun_is_idempotent(raw_repo, content_repo, analysis, brand, load_fixtures):
    load_fixtures(analysis, brand)
    process_analysis_raw_items(raw_repo, content_repo, analysis, windows=WINDOWS)
    stored = content_repo.list_for_analysis(analysis)

    again = process_analysis_raw_items(
        raw_repo, content_repo, analysis, windows=WINDOWS
    )
    assert (again.raw_read, again.kept, again.inserted) == (14, 0, 0)
    assert again.dropped_by_reason() == {DropReason.already_stored: 14}
    assert content_repo.list_for_analysis(analysis) == stored


def test_only_new_raw_items_are_added_on_a_later_run(
    raw_repo, content_repo, analysis, brand, load_fixtures
):
    load_fixtures(analysis, brand)
    process_analysis_raw_items(raw_repo, content_repo, analysis, windows=WINDOWS)
    context = RawItemContext(
        analysis_id=analysis,
        brand_id=brand,
        window=WindowKind.current,
        collected_at=COLLECTED,
    )
    raw_repo.add(
        context,
        _raw(
            title="A brand new story about the Galaxy S25",
            url="https://n.example.test/new",
        ),
    )
    again = process_analysis_raw_items(
        raw_repo, content_repo, analysis, windows=WINDOWS
    )
    assert (again.kept, again.inserted) == (1, 1)
    assert content_repo.count(analysis) == 15


def test_duplicates_syndication_and_bad_rows_are_handled_explicitly(
    raw_repo, content_repo, analysis, brand
):
    context = RawItemContext(
        analysis_id=analysis,
        brand_id=brand,
        window=WindowKind.current,
        collected_at=COLLECTED,
    )
    original = _raw()
    same_page_other_query = _raw(
        url="https://www.wire.example.test/charging/?utm_source=feed",
        query="s25 charging",
        serp_cache_key="k2",
        snippet="Different snippet words entirely.",
    )
    syndicated = _raw(
        title="Samsung confirms charging slowdown on Galaxy S25 Ultra - Example Gadgets",
        author="Example Gadgets",
        url="https://gadgets.example.test/charging",
        snippet="Gadgets coverage of the same story.",
        serp_cache_key="k3",
    )
    bad_url = _raw(
        title="Not fetchable", url="ftp://files.example.test/x", serp_cache_key="k4"
    )
    empty_title = _raw(
        title="<i></i>", url="https://e.example.test/t", serp_cache_key="k5"
    )
    no_snippet = _raw(
        title="Review without a snippet today",
        url="https://r.example.test/x",
        snippet=None,
        published_raw=None,
        serp_cache_key="k6",
    )
    raw_repo.add_many(
        context,
        [original, same_page_other_query, syndicated, bad_url, empty_title, no_snippet],
    )

    result = process_analysis_raw_items(
        raw_repo, content_repo, analysis, windows=WINDOWS
    )
    assert result.raw_read == 6 and result.kept == 3 and result.inserted == 3
    assert result.dropped_by_reason() == {
        DropReason.duplicate_url: 1,
        DropReason.invalid_url: 1,
        DropReason.empty_title: 1,
    }
    assert result.stats.near_duplicate_groups == 1

    stored = content_repo.list_for_analysis(analysis)
    assert len(stored) == 3
    assert content_repo.count_dup_groups(analysis) == 2  # wire + gadgets share a group
    undated = next(s for s in stored if s.title.startswith("Review without"))
    assert undated.snippet is None and undated.date_confidence is DateConfidence.unknown
    assert (
        undated.window is WindowKind.current
    )  # planned window of the call that found it


def test_each_brand_is_deduplicated_on_its_own(
    raw_repo, content_repo, new_brand, analysis, brand, load_fixtures
):
    apple = new_brand("Apple")
    load_fixtures(analysis, brand)
    load_fixtures(analysis, apple)
    result = process_analysis_raw_items(
        raw_repo, content_repo, analysis, windows=WINDOWS
    )
    assert (result.raw_read, result.inserted, result.dropped) == (28, 28, [])
    assert content_repo.count(analysis, brand_id=brand) == 14
    assert content_repo.count(analysis, brand_id=apple) == 14

    only_apple = process_analysis_raw_items(
        raw_repo, content_repo, analysis, windows=WINDOWS, brand_id=apple
    )
    assert only_apple.raw_read == 14 and only_apple.inserted == 0


def test_baseline_call_window_is_used_for_undated_items_only(
    raw_repo, content_repo, analysis, brand
):
    context = RawItemContext(
        analysis_id=analysis,
        brand_id=brand,
        window=WindowKind.baseline,
        collected_at=COLLECTED,
    )
    dated = _raw(published_raw="08/02/2026, 10:15 AM, +0000 UTC", serp_cache_key="k1")
    undated = _raw(
        title="Undated baseline page about phones",
        url="https://u.example.test/1",
        published_raw=None,
        serp_cache_key="k2",
    )
    raw_repo.add_many(context, [dated, undated])
    process_analysis_raw_items(raw_repo, content_repo, analysis, windows=WINDOWS)
    by_title = {i.title: i for i in content_repo.list_for_analysis(analysis)}
    assert by_title[dated.title].window is WindowKind.current  # its date decides
    assert by_title[undated.title].window is WindowKind.baseline


def test_investigation_items_are_processed_without_a_window(
    raw_repo, content_repo, analysis, brand, load_fixtures
):
    load_fixtures(analysis, brand)
    investigation = RawItemContext(
        analysis_id=analysis,
        brand_id=brand,
        purpose=ContentPurpose.investigation,
        collected_at=COLLECTED,
    )
    raw_repo.add(
        investigation,
        _raw(
            title="Investigation finding about charging heat",
            url="https://i.example.test/1",
        ),
    )
    only_inv = process_analysis_raw_items(
        raw_repo,
        content_repo,
        analysis,
        windows=WINDOWS,
        purpose=ContentPurpose.investigation,
    )
    assert (only_inv.raw_read, only_inv.inserted) == (1, 1)
    row = content_repo.list_for_analysis(
        analysis, purpose=ContentPurpose.investigation
    )[0]
    assert row.window is None and content_repo.count(analysis) == 1

    rest = process_analysis_raw_items(raw_repo, content_repo, analysis, windows=WINDOWS)
    assert (
        rest.inserted == 14
    )  # collection rows; the investigation row is already stored
    assert content_repo.count(analysis) == 15


def test_reference_times_anchor_relative_dates(raw_repo, content_repo, analysis, brand):
    context = RawItemContext(
        analysis_id=analysis,
        brand_id=brand,
        window=WindowKind.current,
        collected_at=COLLECTED,
    )
    forum = _raw(
        source_type=SourceType.forum,
        engine=SerpEngine.google_forums,
        title="Battery drain after July update",
        url="https://forum.example.test/t/1",
        published_raw="3 weeks ago",
        serp_cache_key="call-1",
    )
    raw_repo.add(context, forum)
    process_analysis_raw_items(
        raw_repo,
        content_repo,
        analysis,
        windows=WINDOWS,
        reference_times={"call-1": datetime(2026, 7, 10, 12, tzinfo=UTC)},
    )
    row = content_repo.list_for_analysis(analysis)[0]
    assert row.published_at == datetime(2026, 6, 19, 12, tzinfo=UTC)
    assert (
        row.date_confidence is DateConfidence.approximate
        and row.window is WindowKind.baseline
    )


def test_analysis_without_raw_items_is_a_no_op(raw_repo, content_repo, analysis):
    result = process_analysis_raw_items(
        raw_repo, content_repo, analysis, windows=WINDOWS
    )
    assert (result.raw_read, result.kept, result.inserted, result.dropped) == (
        0,
        0,
        0,
        [],
    )


def test_the_stage_never_touches_serpapi():
    """Static guard: no import of the SerpApi client, fetcher, or cache from the stage."""
    tree = ast.parse(inspect.getsource(stage))
    imported = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }
    assert not {m for m in imported if m.startswith("app.services.serpapi")}
