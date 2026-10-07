"""Deterministic scoring constants and pure formulas shared by later pipeline phases."""

import math

EPSILON = 0.02
SIGNAL_WEIGHTS = {"growth": 0.35, "frequency": 0.20, "cross_source": 0.25, "sentiment_impact": 0.20}
HEALTH_WEIGHTS = {"sentiment": 0.35, "engagement": 0.20, "risk": 0.25, "trend": 0.20}
CONFIDENCE_WEIGHTS = {
    "independence": 0.30,
    "agreement": 0.25,
    "signal_strength": 0.20,
    "recency": 0.15,
    "consistency": 0.10,
}


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def growth_ratio(
    current_n: int,
    current_total: int,
    baseline_n: int,
    baseline_total: int,
    epsilon: float = EPSILON,
) -> float:
    """Compute aspect-negative share growth with the documented epsilon smoothing."""
    if min(current_total, baseline_total) <= 0:
        raise ValueError("window totals must be positive")
    if min(current_n, baseline_n) < 0 or current_n > current_total or baseline_n > baseline_total:
        raise ValueError("mention counts must be within their window totals")
    return ((current_n / current_total) + epsilon) / ((baseline_n / baseline_total) + epsilon)


def signal_score(
    growth: float, frequency: float, cross_source: float, sentiment_impact: float
) -> float:
    """Compute the documented signal score from four normalized components."""
    return (
        SIGNAL_WEIGHTS["growth"] * growth
        + SIGNAL_WEIGHTS["frequency"] * frequency
        + SIGNAL_WEIGHTS["cross_source"] * cross_source
        + SIGNAL_WEIGHTS["sentiment_impact"] * sentiment_impact
    )


def health_score(sentiment: int, engagement: int, risk: int, trend: int) -> int:
    """Compute Brand Health and round to the nearest integer."""
    return round(
        HEALTH_WEIGHTS["sentiment"] * sentiment
        + HEALTH_WEIGHTS["engagement"] * engagement
        + HEALTH_WEIGHTS["risk"] * risk
        + HEALTH_WEIGHTS["trend"] * trend
    )


def investigation_confidence(
    independence: float,
    agreement: float,
    signal_strength: float,
    recency: float,
    consistency: float,
) -> int:
    """Compute deterministic investigation confidence, capped at 95."""
    factors = (independence, agreement, signal_strength, recency, consistency)
    if any(not math.isfinite(x) or not 0 <= x <= 1 for x in factors):
        raise ValueError("confidence factors must be finite values in [0, 1]")
    raw = 100 * (
        0.30 * independence
        + 0.25 * agreement
        + 0.20 * signal_strength
        + 0.15 * recency
        + 0.10 * consistency
    )
    return min(95, round(raw))


def net_score(positive: int, negative: int) -> int:
    """Compute aspect net sentiment as positive percentage minus negative percentage."""
    if not 0 <= positive <= 100 or not 0 <= negative <= 100:
        raise ValueError("sentiment percentages must be in [0, 100]")
    return positive - negative
