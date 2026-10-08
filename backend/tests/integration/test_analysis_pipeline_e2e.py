"""End-to-end `run_analysis` against PostgreSQL (skipped without TEST_DATABASE_URL).

Covers the five critical analysis-pipeline fixes: detached ORM instances after commit,
Engine-based Phase 5 repositories, `_snapshot` row unpacking, ORM-vs-schema enum comparison
and the dashboard `role` argument. SerpApi is a `ScriptedTransport` (no network) and the
sentiment model is `StubSentimentAnalyzer` (no torch).
"""

import json
import uuid
from datetime import date
from functools import partial
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config.settings import Settings
from app.db.models.analysis import Analysis
from app.pipeline import analysis_pipeline
from app.pipeline.analysis_pipeline import _brands, _load_context, _snapshot, run_analysis
from app.services.nlp.sentiment import StubSentimentAnalyzer
from app.services.serpapi.client import SerpApiClient
from app.services.serpapi.testing import ScriptedTransport, ok

TRENDS_FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "serpapi"
    / "google_trends_samsung_apple_oneplus.json"
)
TARGET, RIVAL_A, RIVAL_B = "Samsung", "Apple", "OnePlus"
BRANDS = (TARGET, RIVAL_A, RIVAL_B)
CURRENT_DAYS = ("2026-07-20", "2026-07-25", "2026-07-30", "2026-08-03")
BASELINE_DAYS = ("2026-06-15", "2026-06-20", "2026-06-25", "2026-07-02")
COMPLAINTS = (
    "battery drain is bad and annoying",
    "battery life is awful after the update",
    "battery overheating is a terrible bug",
    "battery died fast, disappointed owners",
)
PRAISE = (
    "battery life is excellent",
    "battery is amazing and great",
    "battery lasts long, best in class",
    "battery is brilliant and impressive",
)


def _brand_in(params) -> str:
    query = params.get("q") or params.get("search_query") or ""
    return next(name for name in BRANDS if name.lower() in query.lower())


def _is_current(params) -> bool:
    blob = " ".join(str(v) for v in params.values())
    return "2026-07-12" in blob or "7/12/2026" in blob or "2026-07-1" in blob


def _news(brand: str, current: bool) -> dict:
    days, texts = (CURRENT_DAYS, COMPLAINTS) if current else (BASELINE_DAYS, PRAISE)
    tag = "cur" if current else "base"
    return {
        "news_results": [
            {
                "position": i + 1,
                "title": f"{brand} phone {texts[i]}",
                "link": f"https://news.example.test/{brand.lower()}-{tag}-{i}",
                "source": {"name": f"Outlet {i}"},
                "iso_date": f"{days[i]}T07:00:00Z",
                "snippet": f"{brand} owners discuss why {texts[i]} (report {tag}{i}).",
            }
            for i in range(4)
        ]
    }


def _web(brand: str, current: bool) -> dict:
    days, texts = (CURRENT_DAYS, COMPLAINTS) if current else (BASELINE_DAYS, PRAISE)
    tag = "cur" if current else "base"
    month = {"06": "Jun", "07": "Jul", "08": "Aug"}
    return {
        "organic_results": [
            {
                "position": i + 1,
                "title": f"{brand} review {i}: {texts[(i + 1) % 4]}",
                "link": f"https://reviews.example.test/{brand.lower()}-{tag}-{i}",
                "snippet": f"Our {brand} test shows {texts[i]}.",
                "date": f"{month[days[i][5:7]]} {int(days[i][8:])}, 2026",
                "source": f"Review Site {i}",
            }
            for i in range(4)
        ]
    }


def _script(engine: str, params):
    if engine == "google_trends":
        return ok(json.loads(TRENDS_FIXTURE.read_text()))
    brand = _brand_in(params)
    if engine == "google_news":
        return ok(_news(brand, _is_current(params)))
    if engine == "google":
        return ok(_web(brand, _is_current(params)))
    if engine == "google_forums":
        return ok(
            {
                "organic_results": [
                    {
                        "position": 1,
                        "title": f"{brand} thread: battery drain is bad",
                        "link": f"https://forum.example.test/{brand.lower()}-1",
                        "source": "Forum",
                        "date": "3 weeks ago",
                        "snippet": f"Anyone else with {brand} battery problems?",
                    }
                ]
            }
        )
    return ok(
        {
            "video_results": [
                {
                    "position_on_page": 1,
                    "title": f"{brand} battery test: is it awful?",
                    "link": f"https://www.youtube.example.test/watch?v={brand}1",
                    "channel": {"name": "Tech Channel"},
                    "published_date": "2 weeks ago",
                    "views": 1200,
                    "description": f"We test {brand} battery life.",
                }
            ]
        }
    )


@pytest.fixture
def settings_for(migrated_engine, monkeypatch):
    transport = ScriptedTransport(_script)
    monkeypatch.setattr(
        analysis_pipeline, "SerpApiClient", partial(SerpApiClient, transport=transport)
    )

    class _Hf:
        @staticmethod
        def from_settings(_settings):
            return StubSentimentAnalyzer()

    monkeypatch.setattr(analysis_pipeline, "HFSentimentAnalyzer", _Hf)
    url = migrated_engine.url.render_as_string(hide_password=False)
    return Settings(
        _env_file=None,
        database_url=url,
        serpapi_api_key="test-key",
        allow_live_serpapi=True,
    )


@pytest.fixture
def seeded(migrated_engine):
    """A queued analysis for Samsung with competitors Apple and OnePlus."""
    ids: dict[str, uuid.UUID] = {}
    with migrated_engine.begin() as conn:
        for name in BRANDS:
            ids[name] = conn.execute(
                text(
                    "INSERT INTO brands (name, normalized_name) VALUES (:n, :nn) RETURNING id"
                ),
                {"n": name, "nn": name.lower()},
            ).scalar_one()
        analysis_id = conn.execute(
            text(
                "INSERT INTO analyses (brand_id, product, as_of_date, current_start, "
                "current_end, baseline_start, baseline_end) VALUES (:b, 'Galaxy S25 Ultra', "
                ":a, :cs, :ce, :bs, :be) RETURNING id"
            ),
            {
                "b": ids[TARGET],
                "a": date(2026, 8, 10),
                "cs": date(2026, 7, 12),
                "ce": date(2026, 8, 10),
                "bs": date(2026, 6, 12),
                "be": date(2026, 7, 11),
            },
        ).scalar_one()
        for name, role in ((TARGET, "target"), (RIVAL_A, "competitor"), (RIVAL_B, "competitor")):
            conn.execute(
                text(
                    "INSERT INTO analysis_brands (analysis_id, brand_id, role) "
                    "VALUES (:a, :b, :r)"
                ),
                {"a": analysis_id, "b": ids[name], "r": role},
            )
    return analysis_id, ids


def _scalar(engine, sql: str, **params):
    with engine.connect() as conn:
        return conn.execute(text(sql), params).scalar_one()


def test_full_analysis_with_two_competitors_completes(migrated_engine, settings_for, seeded):
    analysis_id, ids = seeded
    run_analysis(analysis_id, settings_for)

    with migrated_engine.connect() as conn:
        row = conn.execute(
            text("SELECT status, stage, error, progress FROM analyses WHERE id = :a"),
            {"a": analysis_id},
        ).one()
    assert row.error is None
    assert row.status in {"completed", "partial"}
    assert row.stage == "done"
    assert row.progress == 100

    # Competitors are planned, fetched and stored (enum `is` bug dropped them).
    for name in BRANDS:
        n = _scalar(
            migrated_engine,
            "SELECT count(*) FROM content_items WHERE analysis_id = :a AND brand_id = :b",
            a=analysis_id,
            b=ids[name],
        )
        assert n > 0, f"no content_items for {name}"

    # Phase-5 repositories commit: trend points and snapshots are visible to a new connection.
    assert _scalar(
        migrated_engine, "SELECT count(*) FROM trend_points WHERE analysis_id = :a", a=analysis_id
    ) > 0
    with migrated_engine.connect() as conn:
        snaps = {
            r.brand_id: r
            for r in conn.execute(
                text(
                    "SELECT brand_id, sample_size, baseline_sample_size, low_data "
                    "FROM brand_snapshots WHERE analysis_id = :a"
                ),
                {"a": analysis_id},
            )
        }
    assert set(snaps) == set(ids.values())
    for name in BRANDS:
        assert snaps[ids[name]].sample_size > 0, f"empty snapshot for {name}"
    assert snaps[ids[TARGET]].baseline_sample_size > 0


def test_dashboard_returns_200_after_full_run(
    migrated_engine, settings_for, seeded, make_client
):
    analysis_id, ids = seeded
    run_analysis(analysis_id, settings_for)

    client = make_client(
        database_url=settings_for.database_url,
        serpapi_api_key="test-key",
    )
    response = client.get(f"/api/v1/analyses/{analysis_id}/dashboard")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["target"]["brand"]["role"] == "target"
    assert body["target"]["brand"]["name"] == TARGET
    assert body["target"]["sample_size"] > 0
    assert [c["brand"]["role"] for c in body["competitors"]] == ["competitor", "competitor"]
    assert {c["brand"]["name"] for c in body["competitors"]} == {RIVAL_A, RIVAL_B}
    assert all(c["sample_size"] > 0 for c in body["competitors"])


def test_snapshot_counts_items_per_window(migrated_engine, settings_for, seeded):
    """`_snapshot` unpacks (ContentItemRow, ContentAnalysisRow) rows and counts windows."""
    analysis_id, ids = seeded
    run_analysis(analysis_id, settings_for)
    with migrated_engine.begin() as conn:
        conn.execute(text("DELETE FROM brand_snapshots WHERE analysis_id = :a"), {"a": analysis_id})
    with Session(migrated_engine) as session:
        brand = next(b for b in _brands(session, analysis_id) if b.name == TARGET)
        ctx = _load_context(session.get(Analysis, analysis_id))
    _snapshot(migrated_engine, ctx, brand)
    with migrated_engine.connect() as conn:
        snap = conn.execute(
            text(
                "SELECT sample_size, baseline_sample_size, aspect_scores "
                "FROM brand_snapshots WHERE analysis_id = :a AND brand_id = :b"
            ),
            {"a": analysis_id, "b": ids[TARGET]},
        ).one()
    assert snap.sample_size > 0
    assert snap.baseline_sample_size > 0
    assert snap.aspect_scores  # aspect rows were found through the unpacked content ids


def test_run_context_survives_session_close_and_commit(migrated_engine, seeded):
    """The values run_analysis needs after its first session come from plain scalars."""
    analysis_id, _ = seeded
    with Session(migrated_engine) as session:
        analysis = session.get(Analysis, analysis_id)
        analysis.progress = 5
        session.commit()  # expires `analysis`
        ctx = _load_context(analysis)
        brands = _brands(session, analysis_id)
    # Session closed: only plain values are read below.
    assert ctx.analysis_id == analysis_id
    assert ctx.product == "Galaxy S25 Ultra"
    assert ctx.category == "consumer_electronics"
    assert ctx.serp_calls_budget == 12
    assert ctx.windows.as_of_date == date(2026, 8, 10)
    assert ctx.windows.period_days == 30
    assert ctx.windows.baseline_start == date(2026, 6, 12)
    assert sorted((b.name, str(b.role)) for b in brands) == [
        (RIVAL_A, "competitor"),
        (RIVAL_B, "competitor"),
        (TARGET, "target"),
    ]
