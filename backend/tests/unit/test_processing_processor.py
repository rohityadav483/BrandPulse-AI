"""processor: StoredRawItem -> ContentItem over the synthetic SerpApi fixtures. Pure, no DB."""

import re
import uuid
from datetime import UTC, date, datetime

import pytest
from pydantic import ValidationError

from app.schemas.domain import ContentPurpose, DateConfidence, SourceType, WindowKind
from app.schemas.processing import ContentItem, DropReason
from app.schemas.serp import RawItem, SerpEngine, WindowSet
from app.services.processing.normalizer import content_hash, url_hash
from app.services.processing.processor import process_raw_items, to_content_item

ANALYSIS, BRAND = uuid.uuid4(), uuid.uuid4()
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
def all_raw(stored_raw, fixture_raw_items):
    return [
        stored_raw(item, analysis_id=ANALYSIS, brand_id=BRAND)
        for engine in ENGINES
        for item in fixture_raw_items(engine)
    ]


@pytest.fixture
def raw(stored_raw):
    def _make(**fields) -> object:
        values = {
            "source_type": SourceType.web,
            "engine": SerpEngine.google,
            "title": "Galaxy S25 Ultra review",
            "url": "https://reviews.example.test/s25",
            "snippet": "Battery drains fast.",
            "query": "samsung s25 ultra",
        } | fields
        purpose = values.pop("purpose", ContentPurpose.collection)
        window = values.pop("window", WindowKind.current)
        return stored_raw(
            RawItem(**values),
            analysis_id=ANALYSIS,
            brand_id=BRAND,
            purpose=purpose,
            window=window,
        )

    return _make


# ---------- all four engines, end to end ----------


def test_all_fixture_items_become_content_items(all_raw):
    outcome = process_raw_items(all_raw, windows=WINDOWS)
    assert len(all_raw) == 14
    assert len(outcome.items) == 14 and outcome.dropped == []
    assert outcome.stats.raw_in == 14 and outcome.stats.kept == 14 and outcome.stats.dropped == 0
    assert {i.source_type for i in outcome.items} == {
        SourceType.web,
        SourceType.news,
        SourceType.forum,
        SourceType.youtube,
    }


def test_input_order_is_preserved(all_raw):
    outcome = process_raw_items(all_raw, windows=WINDOWS)
    assert [i.title for i in outcome.items] == [r.title for r in all_raw]


def test_every_item_carries_valid_hashes_domain_and_group(all_raw):
    sha = re.compile(r"[0-9a-f]{64}")
    for item in process_raw_items(all_raw, windows=WINDOWS).items:
        assert sha.fullmatch(item.url_hash) and sha.fullmatch(item.content_hash)
        assert sha.fullmatch(item.dup_group)
        assert item.url_hash == url_hash(item.url)
        assert item.content_hash == content_hash(item.title, item.snippet)
        assert item.domain and item.url.startswith("https://")
        assert item.query == "Samsung Galaxy S25 Ultra" and item.serp_cache_key


def test_date_confidence_and_window_counts_over_the_fixtures(all_raw):
    stats = process_raw_items(all_raw, windows=WINDOWS).stats
    # exact: 1 web + 5 news. approximate: 2 forums + 2 youtube. unknown: 2 web + 1 forum + 1 yt.
    assert (stats.date_exact, stats.date_approximate, stats.date_unknown) == (6, 4, 4)
    # YouTube "1 month ago" from Aug 10 12:00 lands on Jul 11 = baseline; the rest are current
    assert (stats.window_current, stats.window_baseline, stats.window_none) == (13, 1, 0)
    assert stats.near_duplicate_groups == 0


def test_news_item_is_normalized_field_by_field(all_raw):
    news = process_raw_items(all_raw, windows=WINDOWS).items[3]
    assert news.engine is SerpEngine.google_news and news.purpose is ContentPurpose.collection
    assert news.url == "https://news.example.test/s25-ultra-battery-drain"
    assert news.domain == "news.example.test"
    assert news.published_at == datetime(2026, 7, 30, 7, tzinfo=UTC)
    assert news.date_confidence is DateConfidence.exact and news.window is WindowKind.current
    assert news.author == "Example Tech Daily"
    assert news.collected_at == datetime(2026, 8, 10, 12, tzinfo=UTC)


def test_youtube_www_and_relative_dates(all_raw):
    first, second, third = process_raw_items(all_raw, windows=WINDOWS).items[-3:]
    assert first.url == "https://youtube.example.test/watch?v=mock0001"
    assert first.domain == "youtube.example.test"
    assert first.date_confidence is DateConfidence.approximate
    assert first.window is WindowKind.current  # "2 weeks ago" = Jul 27
    assert second.window is WindowKind.baseline  # "1 month ago" = Jul 11
    assert third.date_confidence is DateConfidence.unknown and third.published_at is None
    assert third.window is WindowKind.current  # undated -> window of the call that found it


def test_undated_item_keeps_the_planned_window(raw):
    baseline = raw(window=WindowKind.baseline)
    item = process_raw_items([baseline], windows=WINDOWS).items[0]
    assert item.date_confidence is DateConfidence.unknown
    assert item.window is WindowKind.baseline


def test_known_date_overrides_the_planned_window(raw):
    planned_baseline = raw(window=WindowKind.baseline, published_raw="Jul 29, 2026")
    assert process_raw_items([planned_baseline], windows=WINDOWS).items[0].window is (
        WindowKind.current
    )


def test_date_outside_both_windows_is_kept_with_no_window(raw):
    old = raw(published_raw="Jan 5, 2025")
    outcome = process_raw_items([old], windows=WINDOWS)
    assert outcome.dropped == []
    item = outcome.items[0]
    assert item.window is None and item.date_confidence is DateConfidence.exact
    assert outcome.stats.window_none == 1


def test_investigation_items_never_get_a_window(raw):
    inv = raw(purpose=ContentPurpose.investigation, published_raw="Jul 29, 2026")
    item = process_raw_items([inv], windows=WINDOWS).items[0]
    assert item.purpose is ContentPurpose.investigation and item.window is None


def test_without_windows_the_planned_window_is_used(raw):
    item = process_raw_items([raw(published_raw="Jan 5, 2025")], windows=None).items[0]
    assert item.window is WindowKind.current


def test_reference_times_anchor_relative_dates_to_the_serp_call(raw):
    forum = raw(
        source_type=SourceType.forum,
        engine=SerpEngine.google_forums,
        published_raw="3 weeks ago",
        serp_cache_key="call-1",
    )
    default = process_raw_items([forum], windows=WINDOWS).items[0]
    assert default.published_at == datetime(2026, 7, 20, 12, tzinfo=UTC)
    called_earlier = datetime(2026, 7, 10, 12, tzinfo=UTC)
    anchored = process_raw_items(
        [forum], windows=WINDOWS, reference_times={"call-1": called_earlier}
    ).items[0]
    assert anchored.published_at == datetime(2026, 6, 19, 12, tzinfo=UTC)
    assert anchored.window is WindowKind.baseline
    other = process_raw_items(
        [forum], windows=WINDOWS, reference_times={"other-call": called_earlier}
    ).items[0]
    assert other.published_at == default.published_at


# ---------- cleaning ----------


def test_text_is_cleaned_and_blank_snippet_becomes_none(raw):
    item = process_raw_items(
        [raw(title="  <b>S25</b> &amp; friends \n", snippet="  <p> </p> ", author=" Daily  News ")],
        windows=WINDOWS,
    ).items[0]
    assert item.title == "S25 & friends"
    assert item.snippet is None and item.author == "Daily News"


def test_empty_snippet_hashes_like_a_missing_snippet(raw):
    a = to_content_item(raw(snippet=None), windows=WINDOWS)
    b = to_content_item(raw(snippet="  "), windows=WINDOWS)
    assert isinstance(a, ContentItem) and isinstance(b, ContentItem)
    assert a.content_hash == b.content_hash


def test_metadata_and_cache_key_pass_through_unchanged(raw):
    item = to_content_item(
        raw(metadata={"views": 5, "tags": ["a"]}, serp_cache_key="k1"), windows=WINDOWS
    )
    assert item.metadata == {"views": 5, "tags": ["a"]} and item.serp_cache_key == "k1"


def test_missing_query_is_stored_as_empty_string(raw):
    assert to_content_item(raw(query=None), windows=WINDOWS).query == ""


# ---------- drops are explicit ----------


def test_markup_only_title_is_dropped_as_empty_title(raw):
    outcome = process_raw_items([raw(title="<b></b>")], windows=WINDOWS)
    assert outcome.items == []
    assert [d.reason for d in outcome.dropped] == [DropReason.empty_title]


@pytest.mark.parametrize("url", ["ftp://files.example.test/a", "not a url", "https://"])
def test_non_http_urls_are_dropped_as_invalid_url(raw, url):
    item = raw(url=url)
    outcome = process_raw_items([item], windows=WINDOWS)
    assert outcome.items == []
    assert [(d.raw_item_id, d.reason) for d in outcome.dropped] == [
        (item.id, DropReason.invalid_url)
    ]


def test_same_page_from_two_queries_is_one_content_item(raw):
    a = raw(url="https://www.example.test/s25?utm_source=x", query="q1")
    b = raw(
        url="https://example.test/s25/", query="q2", snippet="different words", serp_cache_key="2"
    )
    outcome = process_raw_items([a, b], windows=WINDOWS)
    assert len(outcome.items) == 1
    assert [(d.raw_item_id, d.reason) for d in outcome.dropped] == [
        (b.id, DropReason.duplicate_url)
    ]
    assert outcome.stats.dropped == 1


def test_same_text_on_different_urls_is_dropped_by_content_hash(raw):
    a = raw(url="https://a.example.test/1")
    b = raw(url="https://b.example.test/2", title="GALAXY S25 ULTRA REVIEW!!")
    outcome = process_raw_items([a, b], windows=WINDOWS)
    assert len(outcome.items) == 1
    assert outcome.dropped[0].reason is DropReason.duplicate_content_hash


def test_syndicated_titles_are_kept_but_share_a_dup_group(raw):
    a = raw(
        title="Samsung confirms charging slowdown on S25 Ultra - Example Wire",
        author="Example Wire",
        url="https://wire.example.test/1",
        snippet="one",
    )
    b = raw(
        title="Samsung confirms charging slowdown on S25 Ultra",
        author="Other Outlet",
        url="https://other.example.test/2",
        snippet="two",
    )
    outcome = process_raw_items([a, b], windows=WINDOWS)
    assert len(outcome.items) == 2 and outcome.dropped == []
    assert outcome.items[0].dup_group == outcome.items[1].dup_group
    assert outcome.stats.near_duplicate_groups == 1


def test_already_stored_hashes_are_skipped(raw):
    a, b = raw(), raw(title="Another headline entirely", url="https://x.example.test/b")
    first = process_raw_items([a, b], windows=WINDOWS)
    again = process_raw_items(
        [a, b],
        windows=WINDOWS,
        known_content_hashes={i.content_hash for i in first.items},
        known_url_hashes={i.url_hash for i in first.items},
    )
    assert again.items == []
    assert {d.reason for d in again.dropped} == {DropReason.already_stored}


def test_processing_is_deterministic(all_raw):
    assert process_raw_items(all_raw, windows=WINDOWS) == process_raw_items(
        all_raw, windows=WINDOWS
    )


def test_empty_batch(raw):
    outcome = process_raw_items([], windows=WINDOWS)
    assert outcome.items == [] and outcome.dropped == [] and outcome.stats.raw_in == 0


def test_mixed_brand_batches_are_refused(stored_raw, raw):
    other = stored_raw(
        RawItem(
            source_type=SourceType.web,
            engine=SerpEngine.google,
            title="t",
            url="https://a.example.test",
        ),
        analysis_id=ANALYSIS,
        brand_id=uuid.uuid4(),
    )
    with pytest.raises(ValueError, match="one \\(analysis, brand\\) batch"):
        process_raw_items([raw(), other], windows=WINDOWS)


# ---------- ContentItem contract ----------


def _kwargs(**over):
    return {
        "purpose": ContentPurpose.collection,
        "source_type": SourceType.web,
        "engine": SerpEngine.google,
        "url": "https://a.example.test",
        "url_hash": "a" * 64,
        "domain": "a.example.test",
        "title": "t",
        "date_confidence": DateConfidence.unknown,
        "query": "",
        "content_hash": "b" * 64,
        "collected_at": datetime(2026, 8, 10, tzinfo=UTC),
    } | over


def test_content_item_requires_a_date_exactly_when_confidence_is_not_unknown():
    ContentItem(**_kwargs())
    ContentItem(**_kwargs(date_confidence=DateConfidence.exact, published_at=datetime.now(UTC)))
    with pytest.raises(ValidationError):
        ContentItem(**_kwargs(date_confidence=DateConfidence.exact))
    with pytest.raises(ValidationError):
        ContentItem(**_kwargs(published_at=datetime.now(UTC)))


def test_content_item_investigation_has_no_window():
    with pytest.raises(ValidationError, match="no window"):
        ContentItem(**_kwargs(purpose=ContentPurpose.investigation, window=WindowKind.current))
