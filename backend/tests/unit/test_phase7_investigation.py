from uuid import uuid4

from app.services.investigation.confidence import compute_confidence
from app.services.investigation.query_gen import generate_queries
from app.services.llm.fallback import fallback_report
from app.services.llm.structured import parse_json_object


class Sig:
    aspect = "battery"
    signal_score = 0.8


class E:
    def __init__(self):
        self.id = uuid4()
        self.stance = "supports"


def test_confidence_formula_caps_low_independence():
    x = compute_confidence(
        independence=1,
        agreement=1,
        signal_strength=1,
        recency=1,
        consistency=1,
        independent_sources=1,
    )
    assert x["score"] == 49 and x["label"] == "low"


def test_confidence_high_with_independent_sources():
    x = compute_confidence(
        independence=1,
        agreement=1,
        signal_strength=1,
        recency=1,
        consistency=1,
        independent_sources=4,
    )
    assert x["score"] == 95 and x["label"] == "high"


def test_queries_are_bounded_and_deterministic():
    assert generate_queries(
        "Samsung", "Galaxy S25 Ultra", "battery"
    ) == generate_queries("Samsung", "Galaxy S25 Ultra", "battery")
    assert len(generate_queries("Samsung", None, "battery")) <= 3


def test_structured_json_rejects_non_object():
    try:
        parse_json_object("[1]")
    except (TypeError, ValueError):
        pass
    else:
        raise AssertionError("expected TypeError or ValueError")


def test_fallback_cites_only_supplied_evidence():
    e = E()
    c = {
        "score": 40,
        "label": "low",
        "factors": {
            "independence": 0.25,
            "agreement": 1,
            "signal_strength": 0.8,
            "recency": 0.8,
            "consistency": 1,
        },
    }
    r = fallback_report(Sig(), [e], c)
    ids = {str(e.id)}
    assert all(set(f["evidence_ids"]) <= ids for f in r["findings"])


def test_fallback_no_evidence_is_inconclusive():
    c = {
        "score": 10,
        "label": "low",
        "factors": {
            "independence": 0,
            "agreement": 0,
            "signal_strength": 0.2,
            "recency": 0,
            "consistency": 0,
        },
    }
    r = fallback_report(Sig(), [], c)
    assert r["scope"]["verdict"] == "unknown" and r["findings"] == []
