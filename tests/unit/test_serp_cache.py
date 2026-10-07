from datetime import UTC, datetime, timedelta

import pytest

from app.schemas.serp import QuerySpec, SerpEngine
from app.services.serpapi.cache import (
    EMPTY_RESULT_TTL_HOURS,
    RelativeDateError,
    ResponseCache,
    assert_absolute_dates,
    cache_key,
    normalize_params,
)
from app.services.serpapi.sanitize import sanitize_response
from app.services.serpapi.testing import InMemoryCacheStore, block_network

NOW = datetime(2026, 8, 10, 12, 0, tzinfo=UTC)
SPEC = QuerySpec(engine=SerpEngine.google, params={"q": "Samsung S25", "hl": "en"})
HIT = {"organic_results": [{"title": "t", "link": "https://a.example.test"}]}
EMPTY = {"error": "Google hasn't returned any results for this query."}


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    block_network(monkeypatch)


class Clock:
    def __init__(self):
        self.now = NOW

    def __call__(self):
        return self.now


def make(ttl=720):
    clock = Clock()
    store = InMemoryCacheStore()
    return ResponseCache(store, ttl_hours=ttl, clock=clock), store, clock


def test_key_ignores_api_key_param_order_case_and_spacing():
    a = cache_key("google", {"q": "Samsung  S25", "hl": "en", "api_key": "SECRET"})
    b = cache_key("google", {"hl": "en", "q": "samsung s25"})
    assert a == b and "SECRET" not in a
    assert len(a) == 64


def test_key_changes_with_engine_dates_or_params():
    base = {"q": "x", "tbs": "cdr:1,cd_min:7/12/2026,cd_max:8/10/2026"}
    assert cache_key("google", base) != cache_key("google_news", base)
    shifted = {**base, "tbs": "cdr:1,cd_min:7/13/2026,cd_max:8/10/2026"}
    assert cache_key("google", base) != cache_key("google", shifted)
    as_int, as_str = {"q": "x", "num": 10}, {"q": "x", "num": "10"}
    assert cache_key("google", as_int) == cache_key("google", as_str)
    assert normalize_params({"no_cache": True, "async": False, "x": True}) == {"x": "true"}


@pytest.mark.parametrize(
    "params",
    [
        {"q": "x", "tbs": "qdr:m"},
        {"q": "x", "date": "today 1-m"},
        {"q": "x", "date": "now 7-d"},
        {"q": "x when:7d"},
    ],
)
def test_relative_dates_are_refused(params):
    with pytest.raises(RelativeDateError):
        assert_absolute_dates(QuerySpec(engine=SerpEngine.google, params=params))


def test_absolute_dates_pass():
    params = {"q": "a", "date": "2026-06-12 2026-08-10"}
    assert_absolute_dates(QuerySpec(engine=SerpEngine.google_trends, params=params))


def test_store_then_lookup_hits_and_sanitizes():
    cache, store, _ = make()
    link = "https://serpapi.com/search?api_key=SECRET&start=10"
    dirty = {**HIT, "api_key": "SECRET", "next": link}
    entry = cache.store(SPEC, dirty)
    assert cache.lookup(SPEC) == entry and cache.contains(SPEC)
    blob = str(store.rows[entry.cache_key].model_dump())
    assert "SECRET" not in blob and "api_key=REDACTED" in blob


def test_ttl_expiry_and_empty_result_ttl():
    cache, _, clock = make(ttl=720)
    cache.store(SPEC, HIT)
    clock.now = NOW + timedelta(hours=719)
    assert cache.contains(SPEC)
    clock.now = NOW + timedelta(hours=721)
    assert not cache.contains(SPEC)

    clock.now = NOW
    cache.store(SPEC, EMPTY)
    clock.now = NOW + timedelta(hours=EMPTY_RESULT_TTL_HOURS - 1)
    assert cache.contains(SPEC)
    clock.now = NOW + timedelta(hours=EMPTY_RESULT_TTL_HOURS + 1)
    assert not cache.contains(SPEC)


def test_only_successful_responses_are_cached():
    cache, store, _ = make()
    with pytest.raises(ValueError):
        cache.store(SPEC, HIT, http_status=500)
    with pytest.raises(ValueError):
        cache.store(SPEC, {"error": "Invalid API key."})
    assert store.rows == {}


def test_pinned_entries_never_expire_or_purge_and_survive_refresh():
    cache, store, clock = make(ttl=1)
    assert cache.pin(SPEC) is False  # nothing to pin yet
    cache.store(SPEC, HIT)
    assert cache.pin(SPEC) is True
    clock.now = NOW + timedelta(days=400)
    assert cache.contains(SPEC)
    assert cache.purge_expired() == 0 and len(store.rows) == 1
    cache.store(SPEC, HIT)  # refresh keeps the pin
    assert next(iter(store.rows.values())).pinned is True
    cache.unpin(SPEC)
    clock.now = clock.now + timedelta(hours=2)  # past the refreshed entry's 1h TTL
    assert not cache.contains(SPEC)
    assert cache.purge_expired() == 1 and store.rows == {}


def test_sanitize_response_is_deep():
    clean = sanitize_response({"a": [{"api_key": "k", "u": "x?api_key=abc&y=1"}], "n": 3})
    assert clean == {"a": [{"u": "x?api_key=REDACTED&y=1"}], "n": 3}
