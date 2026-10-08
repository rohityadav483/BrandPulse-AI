"""Phase 5 repositories are Engine-based and commit (skipped without TEST_DATABASE_URL)."""

from datetime import date

from sqlalchemy import text

from app.db.repositories.phase5 import (
    BrandSnapshotRepository,
    SignalRepository,
    TrendPointRepository,
)


def _snapshot_row(analysis_id, brand_id, sample_size=7):
    return {
        "analysis_id": analysis_id,
        "brand_id": brand_id,
        "sample_size": sample_size,
        "baseline_sample_size": 3,
        "sentiment_dist": {"positive": 10, "neutral": 20, "negative": 70},
        "aspect_scores": [],
        "topic_counts": [],
        "source_mix": {"web": sample_size},
        "health": {"overall": 50},
        "interest_change_pct": None,
        "low_data": True,
    }


def _signal_row(analysis_id, brand_id):
    return {
        "analysis_id": analysis_id,
        "brand_id": brand_id,
        "kind": "aspect_negative_spike",
        "aspect": "battery",
        "baseline_n": 1,
        "baseline_total": 10,
        "current_n": 6,
        "current_total": 10,
        "baseline_share": 0.1,
        "current_share": 0.6,
        "growth": 5.0,
        "components": {},
        "signal_score": 80.0,
        "impact": "high",
        "signal_confidence": 70,
        "sources_count": 2,
        "source_types": ["web", "news"],
        "trend_corroborated": False,
    }


def test_trend_points_commit_and_are_visible_to_another_session(
    migrated_engine, new_brand, new_analysis
):
    brand_id = new_brand()
    analysis_id = new_analysis(brand_id)
    repo = TrendPointRepository(migrated_engine)
    rows = [
        {
            "analysis_id": analysis_id,
            "brand_id": brand_id,
            "keyword": "Samsung",
            "date": date(2026, 7, d),
            "value": d,
        }
        for d in (1, 8, 15)
    ]
    assert repo.add_many(rows) == 3
    assert repo.add_many([]) == 0
    with migrated_engine.connect() as conn:  # a different connection sees the committed rows
        count = conn.execute(text("SELECT count(*) FROM trend_points")).scalar_one()
    assert count == 3
    listed = repo.list_for_brand(analysis_id, brand_id, "Samsung")
    assert [p.value for p in listed] == [1, 8, 15]


def test_snapshot_upsert_commits_inserts_then_updates(migrated_engine, new_brand, new_analysis):
    brand_id = new_brand()
    analysis_id = new_analysis(brand_id)
    repo = BrandSnapshotRepository(migrated_engine)
    first = repo.upsert(_snapshot_row(analysis_id, brand_id, 7))
    assert first.sample_size == 7 and first.created_at is not None  # readable after close
    repo.upsert(_snapshot_row(analysis_id, brand_id, 9))
    with migrated_engine.connect() as conn:
        rows = conn.execute(text("SELECT sample_size FROM brand_snapshots")).all()
    assert [r.sample_size for r in rows] == [9]
    assert repo.get(analysis_id, brand_id).sample_size == 9


def test_signals_commit_and_list(migrated_engine, new_brand, new_analysis):
    brand_id = new_brand()
    analysis_id = new_analysis(brand_id)
    repo = SignalRepository(migrated_engine)
    added = repo.add_many([_signal_row(analysis_id, brand_id)])
    assert added[0].id is not None and added[0].aspect == "battery"  # readable after close
    assert repo.add_many([]) == []
    with migrated_engine.connect() as conn:
        count = conn.execute(text("SELECT count(*) FROM signals")).scalar_one()
    assert count == 1
    assert [s.aspect for s in repo.list_for_analysis(analysis_id)] == ["battery"]
    assert repo.get(added[0].id).signal_score == 80.0
