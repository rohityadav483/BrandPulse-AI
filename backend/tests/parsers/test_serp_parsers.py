"""Every engine parser against the recorded/mock fixtures. No network (blocked)."""

import json
from pathlib import Path

import pytest

from app.schemas.domain import SourceType
from app.schemas.serp import QuerySpec, SerpEngine
from app.services.serpapi.cache import cache_key
from app.services.serpapi.parsers import PARSERS, parse_response
from app.services.serpapi.testing import block_network

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "serpapi"


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    block_network(monkeypatch)


def load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def spec_for(engine: SerpEngine, **params) -> QuerySpec:
    return QuerySpec(engine=engine, params=params or {"q": "x"})


def test_every_engine_has_a_parser():
    assert set(PARSERS) == set(SerpEngine)


def test_google_web():
    parsed = parse_response(spec_for(SerpEngine.google), load("google_web_samsung_s25_ultra.json"))
    assert [i.title for i in parsed.items][0] == "Galaxy S25 Ultra review: the good and the bad"
    assert len(parsed.items) == 3
    assert parsed.skipped == 2  # no link, blank title
    first = parsed.items[0]
    assert first.source_type is SourceType.web and first.engine is SerpEngine.google
    assert first.url == "https://reviews.example.test/galaxy-s25-ultra-review"
    assert first.published_raw == "Jul 29, 2026" and first.author == "Example Reviews"
    assert first.position == 1
    assert parsed.items[2].snippet is None


def test_google_news_flattens_story_clusters():
    spec = spec_for(SerpEngine.google_news)
    parsed = parse_response(spec, load("google_news_samsung_s25_ultra.json"))
    titles = [i.title for i in parsed.items]
    assert len(parsed.items) == 5
    assert "Update problems spread across Galaxy S24 and S25 Ultra" in titles
    assert parsed.skipped == 2  # bare string row, row without title
    first = parsed.items[0]
    assert first.source_type is SourceType.news
    assert first.author == "Example Tech Daily"
    assert first.metadata == {"authors": "A. Writer, B. Editor"}
    assert first.published_iso == "2026-07-30T07:00:00Z"
    assert first.published_raw.startswith("07/30/2026")
    assert parsed.items[2].author == "Example Gadgets"  # plain-string source


def test_google_forums():
    spec = spec_for(SerpEngine.google_forums)
    parsed = parse_response(spec, load("google_forums_samsung_s25_ultra.json"))
    assert len(parsed.items) == 3 and parsed.skipped == 1
    first, second, third = parsed.items
    assert first.source_type is SourceType.forum
    assert first.published_raw == "3 weeks ago"
    assert first.metadata == {"answers": 42}
    assert second.author == "phone_fan_77" and second.metadata == {"comments": 17}
    assert third.published_raw is None


def test_youtube():
    parsed = parse_response(spec_for(SerpEngine.youtube), load("youtube_samsung_s25_ultra.json"))
    assert len(parsed.items) == 3 and parsed.skipped == 1
    first, second, third = parsed.items
    assert first.source_type is SourceType.youtube
    assert first.author == "Example Tech Channel"
    assert first.published_raw == "2 weeks ago"
    assert first.metadata["views"] == 120345 and first.metadata["length"] == "12:03"
    assert "views" not in second.metadata  # "1.2K views" is not guessed
    assert third.author is None and third.snippet is None


def test_google_trends():
    parsed = parse_response(
        spec_for(SerpEngine.google_trends), load("google_trends_samsung_apple_oneplus.json")
    )
    assert parsed.items == []
    series = parsed.trends
    assert series.terms == ["Samsung", "Apple", "OnePlus"]
    assert len(series.points) == 3 and parsed.skipped == 1  # the point without a date
    assert series.points[0].values == {"Samsung": 61, "Apple": 88, "OnePlus": 0}  # "<1" -> 0
    assert series.points[2].values["Samsung"] == 100
    assert series.points[0].timestamp == 1780790400
    assert series.averages == {"Samsung": 75, "Apple": 88, "OnePlus": 2}
    assert not parsed.is_empty


@pytest.mark.parametrize("engine", list(SerpEngine))
def test_no_results_payload_parses_to_empty(engine):
    parsed = parse_response(spec_for(engine), load("google_no_results.json"))
    assert parsed.is_empty and parsed.skipped == 0


@pytest.mark.parametrize("engine", list(SerpEngine))
def test_garbage_never_raises(engine):
    payloads = [{}, {"organic_results": "nope", "news_results": [1, None]}, {"video_results": [[]]}]
    for payload in payloads:
        assert parse_response(spec_for(engine), payload).is_empty


def test_items_are_stamped_with_query_and_cache_key():
    spec = spec_for(SerpEngine.youtube, search_query="Samsung Galaxy S25 Ultra")
    key = cache_key(spec.engine, spec.params)
    parsed = parse_response(spec, load("youtube_samsung_s25_ultra.json"), cache_key=key)
    assert {i.query for i in parsed.items} == {"Samsung Galaxy S25 Ultra"}
    assert {i.serp_cache_key for i in parsed.items} == {key}


def test_fixtures_are_marked_synthetic_and_hold_no_secrets():
    files = sorted(FIXTURES.glob("*.json"))
    assert len(files) >= 6
    for path in files:
        raw = path.read_text(encoding="utf-8")
        assert "api_key" not in raw.lower(), path.name
        assert json.loads(raw)["_fixture"]["kind"] in {"synthetic_mock", "recorded"}
