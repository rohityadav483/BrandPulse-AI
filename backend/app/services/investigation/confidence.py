from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime, time

# Evidence loses half of its recency credit every RECENCY_HALF_LIFE_DAYS before the
# analysis `as_of_date`; undated evidence earns none (unknown is not recent).
RECENCY_HALF_LIFE_DAYS = 30.0


def derive_confidence_inputs(evidence, content_by_id, as_of: date) -> dict:
    """Confidence inputs computed from the stored evidence (docs/SCORING.md section 4).

    - independence: distinct domains among supporting evidence, saturating at 4.
    - agreement: share of stance-bearing evidence items that support the signal.
    - recency: mean half-life decay of supporting evidence age (published_at vs `as_of`).
    - consistency: share of stance-bearing domains whose own evidence leans to supporting,
      i.e. agreement across sources rather than across items.
    """
    supporting = [e for e in evidence if e.stance == "supports"]
    contradicting = [e for e in evidence if e.stance == "contradicts"]

    supporting_domains = {
        content_by_id[e.content_id].domain for e in supporting if e.content_id in content_by_id
    }
    stance_total = len(supporting) + len(contradicting)
    agreement = len(supporting) / stance_total if stance_total else 0.0

    reference = datetime.combine(as_of, time.max, tzinfo=UTC)
    credits = []
    for e in supporting:
        item = content_by_id.get(e.content_id)
        published = item.published_at if item is not None else None
        if published is None:
            credits.append(0.0)
            continue
        if published.tzinfo is None:
            published = published.replace(tzinfo=UTC)
        age_days = max(0.0, (reference - published).total_seconds() / 86400)
        credits.append(0.5 ** (age_days / RECENCY_HALF_LIFE_DAYS))
    recency = sum(credits) / len(credits) if credits else 0.0

    tally: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for e in supporting + contradicting:
        item = content_by_id.get(e.content_id)
        if item is not None:
            tally[item.domain][0 if e.stance == "supports" else 1] += 1
    consistency = (
        sum(1 for pro, con in tally.values() if pro > con) / len(tally) if tally else 0.0
    )

    return {
        "independence": min(1.0, len(supporting_domains) / 4),
        "agreement": agreement,
        "recency": recency,
        "consistency": consistency,
        "independent_sources": len(supporting_domains),
    }


def compute_confidence(
    *,
    independence: float,
    agreement: float,
    signal_strength: float,
    recency: float,
    consistency: float,
    independent_sources: int,
) -> dict:
    score = 100 * (
        0.30 * independence
        + 0.25 * agreement
        + 0.20 * signal_strength
        + 0.15 * recency
        + 0.10 * consistency
    )
    if independent_sources < 2:
        score = min(score, 49)
    score = round(max(0, min(95, score)))
    label = "low" if score < 50 else "medium" if score < 75 else "high"
    return {
        "score": score,
        "label": label,
        "factors": {
            "independence": round(independence, 4),
            "agreement": round(agreement, 4),
            "signal_strength": round(signal_strength, 4),
            "recency": round(recency, 4),
            "consistency": round(consistency, 4),
        },
    }
