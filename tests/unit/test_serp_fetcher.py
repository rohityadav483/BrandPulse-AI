import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from app.schemas.serp import SerpEngine, UsagePurpose
from app.services.serpapi.budget import RunBudget, RunBudgetExhausted
from app.services.serpapi.cache import RelativeDateError, ResponseCache
from app.services.serpapi.client import SerpApiClient, TransportResponse
from app.services.serpapi.estimator import estimate_plan
from app.services.serpapi.fetcher import FetchSource, SerpFetcher
from app.services.serpapi.query_planner import build_plan
from app.services.serpapi.testing import (
    InMemoryCacheStore,
    InMemoryUsageStore,
    ScriptedTransport,
    block_network,
    ok,
)
from app.services.serpapi.usage import LiveDataDisabled, MonthlyQuota, QuotaLow

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "serpapi"
NOW = datetime(2026, 10, 6, tzinfo=UTC)
BY_ENGINE = {
    "google": "google_web_samsung_s25_ultra.json",
    "google_news": "google_news_samsung_s25_ultra.json",
    "google_forums": "google_forums_samsung_s25_ultra.json",
    "youtube": "youtube_samsung_s25_ultra.json",
    "google_trends": "google_trends_samsung_apple_oneplus.json",
}


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    block_network(monkeypatch)


def replay(engine, params):
    return ok(json.loads((FIXTURES / BY_ENGINE[engine]).read_text(encoding="utf-8")))


class Rig:
    def __init__(self, script=replay, *, live=True, used=0, limit=250, reserve=20, key="K"):
        self.cache_store = InMemoryCacheStore()
        self.usage_store = InMemoryUsageStore()
        self.transport = ScriptedTransport(script)
        self.cache = ResponseCache(self.cache_store, ttl_hours=720, clock=lambda: NOW)
        self.quota = MonthlyQuota(
            self.usage_store,
            account_label="a",
            limit=limit,
            reserve=reserve,
            allow_live=live,
            clock=lambda: NOW,
        )
        client = SerpApiClient(
            api_key=key,
            allow_live=live,
            transport=self.transport,
            max_retries=0,
            sleep=lambda s: None,
        )
        self.fetcher = SerpFetcher(cache=self.cache, quota=self.quota, client=client)
        for _ in range(used):
            self.quota.record(
                cache_key="old",
                engine="google",
                cache_hit=False,
                credits=1,
                purpose=UsagePurpose.analysis,
            )

    def plan(self, **kw):
        args = {
            "brand": "Samsung",
            "product": "Galaxy S25 Ultra",
            "competitors": ["Apple", "OnePlus"],
            "as_of_date": date(2026, 8, 10),
            "period_days": 30,
            "max_calls": 12,
        }
        return build_plan(**(args | kw))

    def collect(self, plan, cap=12):
        return self.fetcher.collect(plan, budget=RunBudget(cap), purpose=UsagePurpose.analysis)


def test_live_run_fetches_caches_and_logs_one_credit_per_call():
    rig = Rig()
    result = rig.collect(rig.plan())
    assert result.live_calls == 11 and result.cache_hits == 0 and result.complete
    assert len(rig.transport.calls) == 11 and len(rig.cache_store.rows) == 11
    assert [r.credits for r in rig.usage_store.records] == [1] * 11
    assert rig.quota.snapshot().used == 11
    assert all("K" != v for row in rig.cache_store.rows.values() for v in row.params.values())


def test_cache_hit_avoids_a_call_and_costs_nothing():
    rig = Rig()
    plan = rig.plan()
    rig.collect(plan)
    calls_before = len(rig.transport.calls)
    again = rig.collect(plan)
    assert len(rig.transport.calls) == calls_before  # zero new network calls
    assert again.live_calls == 0 and again.cache_hits == 11
    assert all(r.source is FetchSource.cache for _, r in again.fetched)
    assert rig.quota.snapshot().used == 11  # unchanged
    assert sum(1 for r in rig.usage_store.records if r.cache_hit) == 11


def test_cached_replay_works_with_live_switch_off():
    rig = Rig()
    plan = rig.plan()
    rig.collect(plan)
    offline = Rig(live=False)
    offline.cache_store.rows = dict(rig.cache_store.rows)
    result = offline.collect(plan)
    assert result.cache_hits == 11 and result.warnings == [] and offline.transport.calls == []


def test_live_switch_off_blocks_all_network_calls():
    rig = Rig(live=False)
    result = rig.collect(rig.plan())
    assert rig.transport.calls == [] and result.fetched == []
    assert [w.code for w in result.warnings] == ["live_data_disabled"]  # once, not 11 times
    assert len(result.skipped) == 11 and rig.usage_store.records == []
    with pytest.raises(LiveDataDisabled):
        rig.fetcher.fetch(
            rig.plan().calls[0].spec, budget=RunBudget(5), purpose=UsagePurpose.analysis
        )


def test_run_budget_exhaustion_stops_collection_cleanly():
    rig = Rig()
    result = rig.collect(rig.plan(), cap=3)
    assert result.live_calls == 3 and len(rig.transport.calls) == 3
    assert len(result.skipped) == 8 and not result.complete
    assert [w.code for w in result.warnings] == ["serpapi_budget_exhausted"]
    assert {reason for _, reason in result.skipped} == {"serpapi_budget_exhausted"}
    with pytest.raises(RunBudgetExhausted):
        rig.fetcher.fetch(
            rig.plan().calls[5].spec, budget=RunBudget(0), purpose=UsagePurpose.analysis
        )


def test_budget_exhaustion_still_serves_remaining_cache_hits():
    rig = Rig()
    plan = rig.plan()
    for call in plan.calls[-2:]:
        rig.cache.store(call.spec, json.loads((FIXTURES / BY_ENGINE[call.spec.engine]).read_text()))
    result = rig.collect(plan, cap=2)
    assert result.live_calls == 2 and result.cache_hits == 2


def test_reserve_guard_refuses_live_calls_below_the_reserve():
    rig = Rig(used=229)  # 21 left, reserve 20: exactly one live call allowed
    result = rig.collect(rig.plan())
    assert result.live_calls == 1 and len(rig.transport.calls) == 1
    assert [w.code for w in result.warnings] == ["serpapi_budget_exhausted"]
    assert rig.quota.snapshot().remaining == 20
    with pytest.raises(QuotaLow):
        rig.fetcher.fetch(
            rig.plan().calls[3].spec, budget=RunBudget(5), purpose=UsagePurpose.analysis
        )


def test_engine_failure_warns_and_continues_and_logs_zero_credits():
    def script(engine, params):
        return TransportResponse(500, None) if engine == "youtube" else replay(engine, params)

    rig = Rig(script)
    result = rig.collect(rig.plan())
    assert result.live_calls == 10 and len(result.skipped) == 1
    assert [w.code for w in result.warnings] == ["serpapi_engine_failed"]
    failed = [r for r in rig.usage_store.records if r.http_status == 500]
    assert len(failed) == 1 and failed[0].credits == 0 and failed[0].cache_hit is False
    assert rig.quota.snapshot().used == 10


def test_auth_failure_stops_further_live_calls():
    rig = Rig(lambda e, p: TransportResponse(401, {"error": "Invalid API key"}))
    result = rig.collect(rig.plan())
    assert len(rig.transport.calls) == 1  # no blind retries across the plan
    assert len(result.skipped) == 11 and result.live_calls == 0


def test_missing_key_stops_further_live_calls():
    rig = Rig(key="")
    result = rig.collect(rig.plan())
    assert rig.transport.calls == [] and len(result.skipped) == 11


def test_relative_dates_are_refused_before_any_work():
    from app.schemas.serp import QuerySpec

    rig = Rig()
    bad = QuerySpec(engine=SerpEngine.google, params={"q": "x", "tbs": "qdr:w"})
    with pytest.raises(RelativeDateError):
        rig.fetcher.fetch(bad, budget=RunBudget(5), purpose=UsagePurpose.analysis)
    assert rig.transport.calls == [] and rig.usage_store.records == []


def test_estimate_before_matches_what_the_run_actually_spends():
    rig = Rig()
    plan = rig.plan()
    for call in plan.calls[:3]:
        rig.collect(type(plan)(windows=plan.windows, calls=[call]))
    estimate = estimate_plan(plan, rig.cache, rig.quota.snapshot())
    before = rig.quota.snapshot().used
    result = rig.collect(plan)
    assert estimate.estimated_new_calls == result.live_calls == 8
    assert estimate.cached_calls == result.cache_hits == 3
    assert rig.quota.snapshot().used - before == 8


def test_empty_result_is_cached_briefly_and_costs_a_credit():
    body = json.loads((FIXTURES / "google_no_results.json").read_text())
    rig = Rig(lambda e, p: ok(body))
    spec = rig.plan().calls[2].spec
    first = rig.fetcher.fetch(spec, budget=RunBudget(5), purpose=UsagePurpose.probe)
    assert first.credits == 1 and first.source is FetchSource.live
    second = rig.fetcher.fetch(spec, budget=RunBudget(5), purpose=UsagePurpose.probe)
    assert second.cache_hit and rig.quota.snapshot().used == 1
