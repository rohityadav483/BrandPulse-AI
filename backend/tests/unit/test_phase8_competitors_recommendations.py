from types import SimpleNamespace
from uuid import uuid4

from app.services.competitors.comparison import compare_aspect
from app.services.competitors.scope import scope_verdict
from app.services.recommendations.generator import generate_recommendations


def test_scope_verdicts():
    assert scope_verdict(0.75, [0.25, 0.5])["verdict"] == "brand_specific"
    assert scope_verdict(0.20, [0.20, 0.25])["verdict"] == "industry_wide"
    assert scope_verdict(0.49, [0.25, 0.5])["verdict"] == "inconclusive"
    assert scope_verdict(None, [0.5])["verdict"] == "unknown"


def test_comparison_has_target_and_competitors():
    target_id, comp_id = uuid4(), uuid4()
    target = {
        "brand_id": target_id,
        "sample_size": 10,
        "aspects": [{"aspect": "battery", "positive": 10, "negative": 60}],
    }
    comp = {
        "brand_id": comp_id,
        "sample_size": 10,
        "aspects": [{"aspect": "battery", "positive": 40, "negative": 20}],
    }
    refs = {
        target_id: {"id": target_id, "name": "Samsung", "role": "target"},
        comp_id: {"id": comp_id, "name": "Apple", "role": "competitor"},
    }
    rows = compare_aspect(target, [comp], "battery", refs).rows
    assert [r["brand"]["name"] for r in rows] == ["Samsung", "Apple"]
    assert rows[0]["negative_pct"] == 60


def test_recommendation_always_cites_valid_evidence():
    evidence = [SimpleNamespace(id=uuid4()), SimpleNamespace(id=uuid4())]
    signal = SimpleNamespace(
        aspect="battery", impact="high", signal_confidence=80, signal_score=0.8
    )
    recs = generate_recommendations(signal, evidence, {"verdict": "brand_specific"})
    assert recs
    assert recs[0].evidence_ids == [e.id for e in evidence]
    assert recs[0].priority == "high"


def test_no_evidence_means_no_recommendation():
    signal = SimpleNamespace(
        aspect="battery", impact="high", signal_confidence=80, signal_score=0.8
    )
    assert generate_recommendations(signal, [], {"verdict": "brand_specific"}) == []
