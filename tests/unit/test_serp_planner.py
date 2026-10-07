from datetime import date

import pytest

from app.schemas.domain import BrandRole, WindowKind
from app.schemas.serp import SerpEngine
from app.services.serpapi.cache import assert_absolute_dates, cache_key
from app.services.serpapi.query_planner import build_plan, compute_windows, subject_for

AS_OF = date(2026, 8, 10)


def plan(**overrides):
    kwargs = {
        "brand": "Samsung",
        "product": "Galaxy S25 Ultra",
        "competitors": ["Apple", "OnePlus"],
        "as_of_date": AS_OF,
        "period_days": 30,
        "max_calls": 12,
    }
    return build_plan(**(kwargs | overrides))


def test_windows_match_the_api_md_example():
    w = compute_windows(AS_OF, 30)
    assert (w.current_start, w.current_end) == (date(2026, 7, 12), date(2026, 8, 10))
    assert (w.baseline_start, w.baseline_end) == (date(2026, 6, 12), date(2026, 7, 11))


@pytest.mark.parametrize("days", [7, 14, 30])
def test_windows_are_adjacent_equal_spans(days):
    w = compute_windows(AS_OF, days)
    assert (w.current_end - w.current_start).days + 1 == days
    assert (w.baseline_end - w.baseline_start).days + 1 == days
    assert (w.current_start - w.baseline_end).days == 1


def test_bad_period_is_rejected():
    with pytest.raises(ValueError):
        compute_windows(AS_OF, 10)


def test_subject_dedupes_the_brand_prefix():
    assert subject_for("Samsung", "Galaxy S25 Ultra") == "Samsung Galaxy S25 Ultra"
    assert subject_for("Samsung", "Samsung Galaxy S25 Ultra") == "Samsung Galaxy S25 Ultra"
    assert subject_for("Samsung", None) == "Samsung"
    assert subject_for("  Samsung ", "  ") == "Samsung"


def test_lean_plan_is_eleven_calls_with_the_documented_mix():
    p = plan()
    assert p.planned_calls == 11 and p.dropped == []
    by_engine = {}
    for c in p.calls:
        by_engine[c.spec.engine] = by_engine.get(c.spec.engine, 0) + 1
    assert by_engine == {
        SerpEngine.google_news: 4,
        SerpEngine.google: 4,
        SerpEngine.google_forums: 1,
        SerpEngine.youtube: 1,
        SerpEngine.google_trends: 1,
    }
    target = [c for c in p.calls if c.role is BrandRole.target]
    rivals = [c for c in p.calls if c.role is BrandRole.competitor]
    assert len(target) == 7 and len(rivals) == 4
    assert {c.window for c in rivals} == {WindowKind.current}  # competitors: current only


def test_counts_with_fewer_competitors():
    assert plan(competitors=[]).planned_calls == 7
    assert plan(competitors=["Apple"]).planned_calls == 9


def test_trends_is_one_multi_term_call_over_both_windows():
    (trends,) = [c for c in plan().calls if c.spec.engine is SerpEngine.google_trends]
    assert trends.spec.params["q"] == "Samsung,Apple,OnePlus" and trends.window is None
    assert trends.spec.params["date"] == "2026-06-12 2026-08-10"


def test_dates_are_absolute_and_encoded_per_engine():
    p = plan()
    for c in p.calls:
        assert_absolute_dates(c.spec)
    web_cur = next(
        c
        for c in p.calls
        if c.spec.engine is SerpEngine.google
        and c.window is WindowKind.current
        and c.role is BrandRole.target
    )
    assert web_cur.spec.params["tbs"] == "cdr:1,cd_min:7/12/2026,cd_max:8/10/2026"
    assert web_cur.spec.params["q"] == "Samsung Galaxy S25 Ultra review problems"
    news_base = next(
        c
        for c in p.calls
        if c.spec.engine is SerpEngine.google_news and c.window is WindowKind.baseline
    )
    expected = "Samsung Galaxy S25 Ultra after:2026-06-12 before:2026-07-12"
    assert news_base.spec.params["q"] == expected


def test_every_call_has_a_distinct_cache_key():
    keys = [cache_key(c.spec.engine, c.spec.params) for c in plan().calls]
    assert len(set(keys)) == len(keys)


def test_plan_is_deterministic_and_independent_of_today():
    assert plan() == plan()
    assert plan(as_of_date=date(2026, 9, 1)) != plan()


def test_call_cap_drops_the_tail_with_competitors_first():
    p = plan(max_calls=7)
    assert p.planned_calls == 7 and len(p.dropped) == 4
    assert all(c.role is BrandRole.target for c in p.calls)
    assert all(c.role is BrandRole.competitor for c in p.dropped)
    assert plan(max_calls=0).calls == []


def test_invalid_inputs():
    with pytest.raises(ValueError):
        plan(competitors=["A", "B", "C"])
    with pytest.raises(ValueError):
        plan(competitors=["samsung"])
    with pytest.raises(ValueError):
        plan(competitors=["Apple", "apple"])
    with pytest.raises(ValueError):
        plan(max_calls=-1)
