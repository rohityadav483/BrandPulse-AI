"""Signal score, impact and sample-aware confidence."""

from __future__ import annotations

import math

from app.config.scoring_config import clamp, signal_score

FLAG_THRESHOLD = 0.60
HIGH_THRESHOLD = 0.75
MIN_CURRENT_ASPECT = 3
MIN_GROWTH_CURRENT = 12
MIN_ALL_CURRENT = 15


def growth_component(growth: float) -> float:
    if growth <= 0 or not math.isfinite(growth):
        return 0.0
    return clamp(math.log2(growth) / math.log2(5.0))


def score_components(
    growth: float, frequency: float, cross_source: float, sentiment_impact: float
) -> dict[str, float]:
    return {
        "growth": growth_component(growth),
        "frequency": clamp(frequency / 0.25),
        "cross_source": clamp(cross_source),
        "sentiment_impact": clamp(sentiment_impact),
    }


def score_signal(
    growth: float, frequency: float, cross_source: float, sentiment_impact: float
) -> tuple[float, dict[str, float]]:
    components = score_components(growth, frequency, cross_source, sentiment_impact)
    score = signal_score(**components)
    return score, components


def impact_for_score(score: float) -> str | None:
    if score < FLAG_THRESHOLD:
        return None
    return "high" if score >= HIGH_THRESHOLD else "medium"


def signal_confidence(
    *,
    sample_size: int,
    growth_sample_size: int,
    score: float,
    sources_count: int,
    trend_corroborated: bool = False,
) -> int:
    """Deterministic pre-investigation confidence; no LLM input."""
    if sample_size <= 0:
        return 0
    sample_factor = clamp(math.log1p(sample_size) / math.log1p(60))
    growth_factor = clamp(math.log1p(max(growth_sample_size, 0)) / math.log1p(40))
    source_factor = clamp(sources_count / 4.0)
    corroboration = 1.0 if trend_corroborated else 0.0
    raw = 100 * (
        0.40 * sample_factor
        + 0.25 * growth_factor
        + 0.20 * clamp(score)
        + 0.10 * source_factor
        + 0.05 * corroboration
    )
    return min(100, round(raw))
