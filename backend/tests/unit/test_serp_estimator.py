from datetime import UTC, datetime

import pytest

from app.schemas.domain import BlockedReason
from app.schemas.serp import UsagePurpose
from app.services.serpapi.cache import ResponseCache
from app.services.serpapi.estimator import estimate_plan
from app.services.serpapi.query_planner import build_plan
from app.services.serpapi.testing import (
    InMemoryCacheStore,
    InMemoryUsageStore,
    block_network,
)
from app.services.serpapi.usage import MonthlyQuota

NOW = datetime(2026, 10, 6, tzinfo=UTC)
HIT = {"organic_results": [{"title": "t", "link": "https://a.example.test"}]}


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    block_network(monkeypatch)


def setup(*, live=True, used=0, limit=250, reserve=20):
    from datetime import date

    plan = build_plan(
        brand="Samsung",
        product="Galaxy S25 Ultra",
        competitors=["Apple", "OnePlus"],
        as_of_date=date(2026, 8, 10),
        period_days=30,
        max_calls=12,
    )
    cache = ResponseCache(InMemoryCacheStore(), ttl_hours=720, clock=lambda: NOW)
    quota = MonthlyQuota(
        InMemoryUsageStore(),
        account_label="a",
        limit=limit,
        reserve=reserve,
        allow_live=live,
        clock=lambda: NOW,
    )
    for _ in range(used):
        quota.record(
            cache_key="k",
            engine="google",
            cache_hit=False,
            credits=1,
            purpose=UsagePurpose.analysis,
        )
    return plan, cache, quota


def test_empty_cache_estimates_every_call_as_new_and_matches_the_planner():
    plan, cache, quota = setup()
    est = estimate_plan(plan, cache, quota.snapshot())
    assert (est.planned_calls, est.cached_calls, est.estimated_new_calls) == (11, 0, 11)
    assert est.new_calls == plan.calls and est.windows == plan.windows
    assert est.can_run and est.blocked_reason is None and est.live_enabled


def test_cached_calls_are_counted_and_free():
    plan, cache, quota = setup()
    for call in plan.calls[:4]:
        cache.store(call.spec, HIT)
    est = estimate_plan(plan, cache, quota.snapshot())
    assert (est.cached_calls, est.estimated_new_calls) == (4, 7)
    assert est.cached == plan.calls[:4]


def test_fully_cached_run_is_free_even_with_live_off_or_quota_gone():
    plan, cache, quota = setup(live=False, used=250, reserve=20)
    for call in plan.calls:
        cache.store(call.spec, HIT)
    est = estimate_plan(plan, cache, quota.snapshot(), access_code_required=True)
    assert est.estimated_new_calls == 0 and est.can_run and est.blocked_reason is None
    assert est.needs_access_code is False


def test_live_off_blocks_when_new_calls_are_needed():
    plan, cache, quota = setup(live=False)
    est = estimate_plan(plan, cache, quota.snapshot())
    assert not est.can_run and est.blocked_reason is BlockedReason.live_data_disabled


def test_reserve_blocks_when_new_calls_would_dip_below_it():
    plan, cache, quota = setup(used=220)  # 30 left, 11 needed -> 19 < 20
    est = estimate_plan(plan, cache, quota.snapshot())
    assert est.blocked_reason is BlockedReason.serpapi_quota_low and not est.can_run
    plan, cache, quota = setup(used=219)  # 31 left -> exactly the reserve
    assert estimate_plan(plan, cache, quota.snapshot()).can_run


def test_access_code_only_needed_for_new_calls():
    plan, cache, quota = setup()
    assert estimate_plan(
        plan, cache, quota.snapshot(), access_code_required=True
    ).needs_access_code
    assert not estimate_plan(plan, cache, quota.snapshot()).needs_access_code


def test_daily_limit_takes_precedence():
    plan, cache, quota = setup(live=False)
    est = estimate_plan(plan, cache, quota.snapshot(), daily_limit_reached=True)
    assert est.blocked_reason is BlockedReason.daily_limit_reached


def test_estimate_has_no_side_effects():
    plan, cache, quota = setup()
    store = cache._store
    before = (dict(store.rows), len(quota._store.records))
    estimate_plan(plan, cache, quota.snapshot())
    assert (dict(store.rows), len(quota._store.records)) == before
