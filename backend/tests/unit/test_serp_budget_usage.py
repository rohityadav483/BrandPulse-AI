from datetime import UTC, datetime

import pytest

from app.schemas.serp import UsagePurpose
from app.services.serpapi.budget import RunBudget, RunBudgetExhausted
from app.services.serpapi.testing import InMemoryUsageStore, block_network
from app.services.serpapi.usage import (
    LiveDataDisabled,
    MonthlyQuota,
    QuotaLow,
    month_bounds,
    month_label,
)


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    block_network(monkeypatch)


NOW = datetime(2026, 10, 6, 9, 0, tzinfo=UTC)


def quota(
    store=None, *, label="acct-a", limit=250, reserve=20, live=True, clock=lambda: NOW
):
    return MonthlyQuota(
        store or InMemoryUsageStore(),
        account_label=label,
        limit=limit,
        reserve=reserve,
        allow_live=live,
        clock=clock,
    )


def spend(q, n, *, cache_hit=False):
    for _ in range(n):
        q.record(
            cache_key="k",
            engine="google",
            cache_hit=cache_hit,
            credits=0 if cache_hit else 1,
            purpose=UsagePurpose.analysis,
        )


def test_month_bounds_and_label():
    assert month_bounds(NOW) == (
        datetime(2026, 10, 1, tzinfo=UTC),
        datetime(2026, 11, 1, tzinfo=UTC),
    )
    _, december_end = month_bounds(datetime(2026, 12, 31, 23, tzinfo=UTC))
    assert december_end == datetime(2027, 1, 1, tzinfo=UTC)
    assert month_label(NOW) == "2026-10"


def test_snapshot_counts_credits_not_cache_hits():
    q = quota()
    spend(q, 3)
    spend(q, 5, cache_hit=True)
    snap = q.snapshot()
    assert (snap.limit, snap.used, snap.remaining, snap.reserve) == (250, 3, 247, 20)
    assert snap.month == "2026-10" and snap.live_enabled is True


def test_reserve_guard_boundaries():
    q = quota(limit=250, reserve=20)
    spend(q, 229)  # 21 left: one more call leaves exactly the reserve
    q.check_live()
    spend(q, 1)  # 20 left: next call would dip below the reserve
    with pytest.raises(QuotaLow) as err:
        q.check_live()
    assert (err.value.remaining, err.value.reserve) == (20, 20)
    with pytest.raises(QuotaLow):
        quota(limit=10, reserve=3).check_live(8)


def test_live_switch_off_blocks_before_touching_the_store():
    class Exploding:
        def monthly_credits(self, *a):
            raise AssertionError("store must not be read when live is off")

        def add(self, record):
            raise AssertionError

    with pytest.raises(LiveDataDisabled):
        quota(Exploding(), live=False).check_live()


def test_account_label_starts_a_clean_count():
    store = InMemoryUsageStore()
    spend(quota(store, label="old"), 200)
    assert quota(store, label="old").snapshot().used == 200
    assert quota(store, label="new").snapshot().used == 0


def test_new_month_starts_a_clean_count():
    store = InMemoryUsageStore()
    spend(quota(store), 40)
    november = datetime(2026, 11, 2, tzinfo=UTC)
    assert quota(store, clock=lambda: november).snapshot().used == 0


def test_remaining_never_negative():
    q = quota(limit=5, reserve=0)
    spend(q, 9)
    assert q.snapshot().remaining == 0


def test_reserve_above_limit_is_rejected():
    with pytest.raises(ValueError):
        quota(limit=10, reserve=11)


def test_run_budget_caps_live_calls():
    b = RunBudget(2)
    b.consume()
    b.consume()
    assert b.spent == 2 and b.remaining == 0
    with pytest.raises(RunBudgetExhausted) as err:
        b.check()
    assert err.value.cap == 2
    with pytest.raises(ValueError):
        RunBudget(-1)
    RunBudget(0).check(0)
