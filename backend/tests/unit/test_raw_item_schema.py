"""RawItem contract: validation, exact-occurrence key, context rules. Pure, no DB, no network."""

import json
import re
import uuid
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.schemas.domain import ContentPurpose, SourceType, WindowKind
from app.schemas.serp import (
    ENGINE_SOURCE_TYPE,
    QuerySpec,
    RawItem,
    RawItemContext,
    RawItemWriteResult,
    SerpEngine,
)
from app.services.serpapi.cache import cache_key
from app.services.serpapi.parsers import parse_response

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "serpapi"
CONTENT_FIXTURES = {
    SerpEngine.google: "google_web_samsung_s25_ultra.json",
    SerpEngine.google_news: "google_news_samsung_s25_ultra.json",
    SerpEngine.google_forums: "google_forums_samsung_s25_ultra.json",
    SerpEngine.youtube: "youtube_samsung_s25_ultra.json",
}
ANALYSIS, BRAND = uuid.uuid4(), uuid.uuid4()


def parsed_items(engine: SerpEngine) -> list[RawItem]:
    param = "search_query" if engine is SerpEngine.youtube else "q"
    spec = QuerySpec(engine=engine, params={param: "Samsung Galaxy S25 Ultra"})
    response = json.loads(
        (FIXTURES / CONTENT_FIXTURES[engine]).read_text(encoding="utf-8")
    )
    return parse_response(
        spec, response, cache_key=cache_key(spec.engine, spec.params)
    ).items


def make(**overrides) -> RawItem:
    values = {
        "source_type": SourceType.web,
        "engine": SerpEngine.google,
        "title": "Galaxy S25 Ultra review",
        "url": "https://reviews.example.test/s25",
        "snippet": "Battery drains fast.",
        "published_raw": "3 weeks ago",
        "position": 2,
        "query": "samsung s25 ultra",
        "serp_cache_key": "k1",
    } | overrides
    return RawItem(**values)


# ---------- every SerpApi content source fits the one contract ----------


@pytest.mark.parametrize("engine", list(CONTENT_FIXTURES))
def test_every_content_engine_fixture_yields_valid_raw_items(engine):
    items = parsed_items(engine)
    assert items
    for item in items:
        assert RawItem.model_validate(item.model_dump()) == item
        assert item.engine is engine
        assert item.source_type is ENGINE_SOURCE_TYPE[engine]
        assert re.fullmatch(r"[0-9a-f]{64}", item.compute_raw_key())


def test_raw_items_from_all_engines_cover_the_four_content_source_types():
    seen = {
        item.source_type for engine in CONTENT_FIXTURES for item in parsed_items(engine)
    }
    assert seen == {
        SourceType.web,
        SourceType.news,
        SourceType.forum,
        SourceType.youtube,
    }


@pytest.mark.parametrize("engine", list(CONTENT_FIXTURES))
def test_raw_keys_are_unique_within_a_response_and_stable_across_parses(engine):
    first = [i.compute_raw_key() for i in parsed_items(engine)]
    second = [i.compute_raw_key() for i in parsed_items(engine)]
    assert first == second
    assert len(set(first)) == len(first)


# ---------- validation ----------


def test_trends_engine_cannot_be_a_raw_item():
    with pytest.raises(ValidationError, match="does not produce RawItems"):
        make(engine=SerpEngine.google_trends)


@pytest.mark.parametrize(
    ("engine", "wrong"),
    [
        (SerpEngine.google, SourceType.news),
        (SerpEngine.google_news, SourceType.web),
        (SerpEngine.google_forums, SourceType.youtube),
        (SerpEngine.youtube, SourceType.forum),
        (SerpEngine.google, SourceType.shopping),
    ],
)
def test_source_type_must_match_engine(engine, wrong):
    with pytest.raises(ValidationError, match="yields source_type"):
        make(engine=engine, source_type=wrong)


@pytest.mark.parametrize("field", ["title", "url"])
@pytest.mark.parametrize("value", ["", "   ", "\n\t "])
def test_blank_title_or_url_is_rejected(field, value):
    with pytest.raises(ValidationError):
        make(**{field: value})


@pytest.mark.parametrize("position", [0, -3])
def test_position_must_be_positive(position):
    with pytest.raises(ValidationError):
        make(position=position)


def test_validation_never_modifies_values():
    item = make(
        title="  Padded Title \n", url=" HTTPS://Example.TEST/A?utm=1 ", snippet="  "
    )
    assert item.title == "  Padded Title \n"
    assert item.url == " HTTPS://Example.TEST/A?utm=1 "
    assert item.snippet == "  "


def test_optional_fields_default_to_none_or_empty():
    item = RawItem(
        source_type=SourceType.news,
        engine=SerpEngine.google_news,
        title="t",
        url="https://a.example.test",
    )
    assert (
        item.snippet is item.author is item.published_raw is item.published_iso is None
    )
    assert item.position is item.query is item.serp_cache_key is None
    assert item.metadata == {}


# ---------- raw_key: exact occurrence, no normalisation ----------


def test_raw_key_is_deterministic():
    assert make().compute_raw_key() == make().compute_raw_key()


@pytest.mark.parametrize(
    "change",
    [
        {"title": "Galaxy S25 Ultra review!"},
        {"url": "https://reviews.example.test/s25/"},
        {
            "url": "https://REVIEWS.example.test/s25"
        },  # no canonicalisation: case matters
        {"snippet": "Battery drains fast"},
        {"snippet": None},
        {"published_raw": "4 weeks ago"},
        {"published_iso": "2026-07-30T07:00:00Z"},
        {"position": 3},
        {"query": "samsung s25 ultra battery"},
        {"serp_cache_key": "k2"},
        {"title": "Galaxy S25 Ultra review "},  # no whitespace cleanup
    ],
)
def test_raw_key_changes_when_any_identifying_field_changes(change):
    assert make(**change).compute_raw_key() != make().compute_raw_key()


@pytest.mark.parametrize(
    "change", [{"author": "Someone Else"}, {"metadata": {"views": 5}}]
)
def test_raw_key_ignores_author_and_metadata(change):
    assert make(**change).compute_raw_key() == make().compute_raw_key()


def test_raw_key_has_no_field_boundary_collisions():
    a = make(title="ab", snippet="c")
    b = make(title="a", snippet="bc")
    assert a.compute_raw_key() != b.compute_raw_key()


def test_raw_key_distinguishes_none_from_empty_string():
    assert make(snippet=None).compute_raw_key() != make(snippet="").compute_raw_key()


def test_raw_key_handles_non_ascii():
    assert (
        make(title="Galaxy – 배터리 🔋").compute_raw_key() != make().compute_raw_key()
    )


# ---------- RawItemContext ----------


def test_collection_context_requires_window():
    with pytest.raises(ValidationError, match="need a window"):
        RawItemContext(analysis_id=ANALYSIS, brand_id=BRAND)
    ctx = RawItemContext(
        analysis_id=ANALYSIS, brand_id=BRAND, window=WindowKind.current
    )
    assert ctx.purpose is ContentPurpose.collection and ctx.collected_at is None


def test_investigation_context_has_no_window():
    ctx = RawItemContext(
        analysis_id=ANALYSIS, brand_id=BRAND, purpose=ContentPurpose.investigation
    )
    assert ctx.window is None
    with pytest.raises(ValidationError, match="no window"):
        RawItemContext(
            analysis_id=ANALYSIS,
            brand_id=BRAND,
            purpose=ContentPurpose.investigation,
            window=WindowKind.baseline,
        )


def test_context_is_frozen():
    ctx = RawItemContext(
        analysis_id=ANALYSIS, brand_id=BRAND, window=WindowKind.current
    )
    with pytest.raises(ValidationError):
        ctx.window = WindowKind.baseline


def test_write_result_total():
    assert RawItemWriteResult(inserted=3, duplicates=2).total == 5
