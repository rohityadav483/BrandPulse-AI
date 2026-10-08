# ruff: noqa: F811
"""`run_analysis` uses the analysed product for relevance and the stored Trends data.

Content comes from the scripted analysis fixtures. Two extra web results are added to the
Samsung current window: one about another brand (off topic) and one that names only the
analysed product ("Galaxy S25 Ultra", no brand name). Trends are replaced by daily series
with a known change per brand.
"""

import json
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import text

import test_analysis_pipeline_e2e as base
from test_analysis_pipeline_e2e import (  # noqa: F401  (fixtures)
    RIVAL_A,
    RIVAL_B,
    TARGET,
    run_analysis,
    seeded,
    settings_for,
)

OFF_TOPIC_URL = "https://reviews.example.test/pixel-offtopic"
PRODUCT_ONLY_URL = "https://reviews.example.test/s25-ultra-only"


def _trends_json(levels: dict[str, tuple[int, int]]) -> dict:
    """Daily-ish points: `levels[brand] = (baseline value, current value)`."""
    days = [date(2026, 6, 12) + timedelta(days=5 * i) for i in range(12)]  # Jun 12 .. Aug 6
    timeline = []
    for d in days:
        in_current = d >= date(2026, 7, 12)
        ts = int(datetime(d.year, d.month, d.day, tzinfo=UTC).timestamp())
        timeline.append(
            {
                "date": d.strftime("%b %d, %Y"),
                "timestamp": str(ts),
                "values": [
                    {
                        "query": name,
                        "value": str(vals[1 if in_current else 0]),
                        "extracted_value": vals[1 if in_current else 0],
                    }
                    for name, vals in levels.items()
                ],
            }
        )
    return {"interest_over_time": {"timeline_data": timeline}}


@pytest.fixture
def trend_levels(tmp_path, monkeypatch):
    levels = {TARGET: (40, 60), RIVAL_A: (50, 50), RIVAL_B: (40, 20)}
    path = tmp_path / "trends.json"
    path.write_text(json.dumps(_trends_json(levels)))
    monkeypatch.setattr(base, "TRENDS_FIXTURE", path)
    return levels


@pytest.fixture
def spiky_items(monkeypatch):
    """16 dated news/web items per window and brand: praise in baseline, complaints now."""

    def build(brand, current, kind):
        texts = base.COMPLAINTS if current else base.PRAISE
        start = date(2026, 7, 14) if current else date(2026, 6, 14)
        tag = "cur" if current else "base"
        out = []
        for i in range(8):
            d = start + timedelta(days=2 * i)
            body = f"{brand} phone {texts[i % 4]} (note {kind}-{tag}-{i})"
            if kind == "news":
                out.append(
                    {
                        "position": i + 1,
                        "title": body,
                        "link": f"https://news.example.test/{brand.lower()}-{tag}-{i}",
                        "source": {"name": f"Outlet {i}"},
                        "iso_date": f"{d.isoformat()}T07:00:00Z",
                        "snippet": f"{brand} owners discuss {texts[i % 4]} ({tag}{i}).",
                    }
                )
            else:
                out.append(
                    {
                        "position": i + 1,
                        "title": body,
                        "link": f"https://reviews.example.test/{brand.lower()}-{tag}-{i}",
                        "snippet": f"Our {brand} test shows {texts[i % 4]} ({tag}{i}).",
                        "date": f"{d.strftime('%b')} {d.day}, 2026",
                        "source": f"Review Site {i}",
                    }
                )
        return out

    monkeypatch.setattr(
        base, "_news", lambda brand, current: {"news_results": build(brand, current, "news")}
    )
    monkeypatch.setattr(
        base, "_web", lambda brand, current: {"organic_results": build(brand, current, "web")}
    )


@pytest.fixture
def extra_web_items(monkeypatch):
    real = base._web

    def web(brand, current):
        data = real(brand, current)
        if brand == TARGET and current:
            data["organic_results"] += [
                {
                    "position": 5,
                    "title": "Pixel 10 battery drain is bad and annoying",
                    "link": OFF_TOPIC_URL,
                    "snippet": "Google phone owners complain about battery drain.",
                    "date": "Jul 22, 2026",
                    "source": "Review Site X",
                },
                {
                    "position": 6,
                    "title": "Galaxy S25 Ultra battery is awful",
                    "link": PRODUCT_ONLY_URL,
                    "snippet": "The Galaxy S25 Ultra battery died fast.",
                    "date": "Jul 23, 2026",
                    "source": "Review Site Y",
                },
            ]
        return data

    monkeypatch.setattr(base, "_web", web)


def _about(engine, url):
    with engine.connect() as conn:
        return conn.execute(
            text(
                "SELECT ca.is_about_brand, ca.matched_terms, "
                "(SELECT count(*) FROM item_aspects ia WHERE ia.content_id = ci.id) AS aspects "
                "FROM content_items ci JOIN content_analysis ca ON ca.content_id = ci.id "
                "WHERE ci.url = :u"
            ),
            {"u": url},
        ).one_or_none()


def test_product_makes_item_relevant_and_off_topic_item_is_excluded(
    migrated_engine, settings_for, seeded, extra_web_items, trend_levels
):
    analysis_id, ids = seeded
    run_analysis(analysis_id, settings_for)

    off = _about(migrated_engine, OFF_TOPIC_URL)
    assert off is not None and off.is_about_brand is False
    assert off.aspects == 0  # no aspect observations from an off-topic item

    product_only = _about(migrated_engine, PRODUCT_ONLY_URL)
    assert product_only is not None and product_only.is_about_brand is True
    assert product_only.matched_terms == ["Galaxy S25 Ultra"]

    # The snapshot counts only items about the brand, and only in the current window.
    with migrated_engine.connect() as conn:
        counted = conn.execute(
            text(
                "SELECT count(*) FROM content_items ci "
                "JOIN content_analysis ca ON ca.content_id = ci.id "
                "WHERE ci.analysis_id = :a AND ci.brand_id = :b AND ci.purpose = 'collection' "
                "AND ci.\"window\" = 'current' AND ca.is_about_brand"
            ),
            {"a": analysis_id, "b": ids[TARGET]},
        ).scalar_one()
        everything = conn.execute(
            text(
                "SELECT count(*) FROM content_items WHERE analysis_id = :a AND brand_id = :b "
                "AND purpose = 'collection' AND \"window\" = 'current'"
            ),
            {"a": analysis_id, "b": ids[TARGET]},
        ).scalar_one()
        sample = conn.execute(
            text("SELECT sample_size FROM brand_snapshots WHERE analysis_id = :a AND brand_id = :b"),
            {"a": analysis_id, "b": ids[TARGET]},
        ).scalar_one()
    assert everything == counted + 1  # exactly the off-topic item is left out
    assert sample == counted


def test_product_is_not_applied_to_competitors(migrated_engine, settings_for, seeded, monkeypatch):
    from app.pipeline.analysis_pipeline import _BrandCtx, _brand_profile

    target = _BrandCtx(id=seeded[1][TARGET], name=TARGET, role="target")
    rival = _BrandCtx(id=seeded[1][RIVAL_A], name=RIVAL_A, role="competitor")
    assert _brand_profile(target, "Galaxy S25 Ultra").products == ("Galaxy S25 Ultra",)
    assert _brand_profile(rival, "Galaxy S25 Ultra").products == ()
    assert _brand_profile(target, None).products == ()


def test_trend_points_are_stored_under_their_own_brand(
    migrated_engine, settings_for, seeded, trend_levels
):
    analysis_id, ids = seeded
    run_analysis(analysis_id, settings_for)
    with migrated_engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT brand_id, keyword, count(*) AS n FROM trend_points "
                "WHERE analysis_id = :a GROUP BY brand_id, keyword"
            ),
            {"a": analysis_id},
        ).all()
    assert {(r.brand_id, r.keyword) for r in rows} == {(ids[n], n) for n in base.BRANDS}
    assert all(r.n == 12 for r in rows)


def test_interest_change_reaches_snapshots_health_and_dashboard(
    migrated_engine, settings_for, seeded, trend_levels, make_client
):
    analysis_id, ids = seeded
    run_analysis(analysis_id, settings_for)
    with migrated_engine.connect() as conn:
        snaps = {
            r.brand_id: r
            for r in conn.execute(
                text(
                    "SELECT brand_id, interest_change_pct, health FROM brand_snapshots "
                    "WHERE analysis_id = :a"
                ),
                {"a": analysis_id},
            )
        }
    assert snaps[ids[TARGET]].interest_change_pct == pytest.approx(50.0)
    assert snaps[ids[RIVAL_A]].interest_change_pct == pytest.approx(0.0)
    assert snaps[ids[RIVAL_B]].interest_change_pct == pytest.approx(-50.0)
    # Health "trend" now follows search interest instead of a constant.
    trend = {n: snaps[ids[n]].health["trend"] for n in base.BRANDS}
    assert trend[TARGET] > trend[RIVAL_A] > trend[RIVAL_B]

    client = make_client(database_url=settings_for.database_url, serpapi_api_key="test-key")
    body = client.get(f"/api/v1/analyses/{analysis_id}/dashboard").json()
    interest = body["target"]["search_interest"]
    assert interest["change_pct"] == pytest.approx(50.0)
    assert len(interest["series"]) == 12 and interest["series"][0]["date"] == "2026-06-12"
    by_name = {c["brand"]["name"]: c for c in body["competitors"]}
    assert by_name[RIVAL_B]["search_interest"]["change_pct"] == pytest.approx(-50.0)
    assert by_name[RIVAL_A]["search_interest"]["series"]


def test_dashboard_search_interest_is_null_without_trends_data(
    migrated_engine, settings_for, seeded, monkeypatch, make_client
):
    analysis_id, ids = seeded
    # No Trends call in the plan -> no points, no change, no series.
    monkeypatch.setattr(
        base, "TRENDS_FIXTURE", base.TRENDS_FIXTURE.with_name("google_no_results.json")
    )
    run_analysis(analysis_id, settings_for)
    client = make_client(database_url=settings_for.database_url, serpapi_api_key="test-key")
    body = client.get(f"/api/v1/analyses/{analysis_id}/dashboard").json()
    assert body["target"]["search_interest"] is None
    with migrated_engine.connect() as conn:
        change = conn.execute(
            text("SELECT interest_change_pct FROM brand_snapshots WHERE brand_id = :b"),
            {"b": ids[TARGET]},
        ).scalar_one()
    assert change is None


@pytest.mark.parametrize(
    ("levels", "expected"),
    [({TARGET: (40, 60), RIVAL_A: (50, 50), RIVAL_B: (40, 20)}, True), ({TARGET: (60, 40)}, False)],
)
def test_signal_trend_corroboration_follows_search_interest(
    migrated_engine, settings_for, seeded, tmp_path, monkeypatch, levels, expected, spiky_items
):
    path = tmp_path / "t.json"
    path.write_text(json.dumps(_trends_json({**{RIVAL_A: (50, 50), RIVAL_B: (40, 20)}, **levels})))
    monkeypatch.setattr(base, "TRENDS_FIXTURE", path)
    analysis_id, ids = seeded
    run_analysis(analysis_id, settings_for)
    with migrated_engine.connect() as conn:
        flags = conn.execute(
            text("SELECT trend_corroborated FROM signals WHERE brand_id = :b"),
            {"b": ids[TARGET]},
        ).scalars().all()
    assert flags, "the scripted data should produce at least one Samsung signal"
    assert set(flags) == {expected}
