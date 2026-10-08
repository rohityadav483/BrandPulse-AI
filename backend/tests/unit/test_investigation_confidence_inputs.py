"""Confidence inputs are derived from stored evidence, not placeholders."""

from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace as NS
from uuid import uuid4

import pytest

from app.services.investigation.confidence import (
    RECENCY_HALF_LIFE_DAYS,
    compute_confidence,
    derive_confidence_inputs,
)

AS_OF = date(2026, 8, 10)


def _ev(stance, content_id):
    return NS(stance=stance, content_id=content_id)


def _item(domain, days_old):
    published = (
        None
        if days_old is None
        else datetime(2026, 8, 10, tzinfo=UTC) - timedelta(days=days_old)
    )
    return NS(id=uuid4(), domain=domain, published_at=published)


def _derive(spec):
    """spec: [(stance, domain, days_old)]"""
    items = [_item(d, age) for _s, d, age in spec]
    evidence = [_ev(s, i.id) for (s, _d, _a), i in zip(spec, items, strict=True)]
    return derive_confidence_inputs(evidence, {i.id: i for i in items}, AS_OF)


def test_recency_depends_on_evidence_dates():
    fresh = _derive([("supports", "a.com", 1), ("supports", "b.com", 2)])
    stale = _derive([("supports", "a.com", 200), ("supports", "b.com", 300)])
    assert fresh["recency"] > 0.9
    assert stale["recency"] < 0.02
    assert fresh["recency"] != 0.8 and stale["recency"] != 0.8


def test_recency_halves_every_half_life_and_undated_evidence_earns_nothing():
    one = _derive([("supports", "a.com", RECENCY_HALF_LIFE_DAYS)])
    assert one["recency"] == pytest.approx(0.5, abs=0.02)
    mixed = _derive([("supports", "a.com", 0), ("supports", "b.com", None)])
    assert mixed["recency"] == pytest.approx(0.5, abs=0.02)


def test_consistency_is_cross_source_agreement_not_item_agreement():
    # 3 supporting items from one domain vs 1 contradicting item each from two others:
    # item agreement is 3/5 but only 1 of 3 sources leans to supporting.
    got = _derive(
        [
            ("supports", "a.com", 1),
            ("supports", "a.com", 2),
            ("supports", "a.com", 3),
            ("contradicts", "b.com", 1),
            ("contradicts", "c.com", 1),
        ]
    )
    assert got["agreement"] == pytest.approx(0.6)
    assert got["consistency"] == pytest.approx(1 / 3)
    assert got["consistency"] != got["agreement"]


def test_independence_counts_distinct_supporting_domains_only():
    got = _derive(
        [
            ("supports", "a.com", 1),
            ("supports", "a.com", 2),
            ("supports", "b.com", 1),
            ("contradicts", "c.com", 1),
            ("neutral", "d.com", 1),
        ]
    )
    assert got["independent_sources"] == 2
    assert got["independence"] == pytest.approx(0.5)


def test_no_evidence_gives_zero_inputs_and_low_confidence():
    got = derive_confidence_inputs([], {}, AS_OF)
    assert got == {
        "independence": 0.0,
        "agreement": 0.0,
        "recency": 0.0,
        "consistency": 0.0,
        "independent_sources": 0,
    }
    assert compute_confidence(signal_strength=0.8, **got)["label"] == "low"


def test_different_evidence_dates_change_the_final_score():
    spec = lambda age: [  # noqa: E731
        ("supports", "a.com", age),
        ("supports", "b.com", age),
        ("supports", "c.com", age),
    ]
    new = compute_confidence(signal_strength=0.8, **_derive(spec(1)))
    old = compute_confidence(signal_strength=0.8, **_derive(spec(400)))
    assert new["score"] > old["score"]
    assert new["factors"]["recency"] > old["factors"]["recency"]


def test_single_domain_is_forced_low():
    got = _derive([("supports", "a.com", 0)] * 3)
    assert compute_confidence(signal_strength=1.0, **got)["label"] == "low"
