"""MVP aspect-negative-spike detector."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from app.services.signals.metrics import MetricItem, compute_window_metrics
from app.services.signals.scoring import (
    MIN_ALL_CURRENT,
    MIN_CURRENT_ASPECT,
    MIN_GROWTH_CURRENT,
    impact_for_score,
    score_signal,
    signal_confidence,
)


@dataclass(frozen=True)
class SignalCandidate:
    kind: str
    aspect: str
    baseline_n: int
    baseline_total: int
    current_n: int
    current_total: int
    baseline_share: float
    current_share: float
    growth: float
    components: dict[str, float]
    score: float
    impact: str
    confidence: int
    sources_count: int
    source_types: tuple[str, ...]


def detect_negative_spike(
    items: Iterable[MetricItem], aspect: str, *, trend_corroborated: bool = False
) -> SignalCandidate | None:
    rows = list(items)
    metrics = compute_window_metrics(rows, aspect)
    all_current = sum(x.window == "current" and x.is_about_brand for x in rows)
    if (
        metrics.current_n < MIN_CURRENT_ASPECT
        or metrics.growth_current_total < MIN_GROWTH_CURRENT
        or all_current < MIN_ALL_CURRENT
    ):
        return None
    if metrics.growth is None:
        return None
    score, components = score_signal(
        metrics.growth,
        metrics.frequency,
        metrics.cross_source,
        metrics.sentiment_impact,
    )
    impact = impact_for_score(score)
    if impact is None:
        return None
    return SignalCandidate(
        kind="aspect_negative_spike",
        aspect=aspect,
        baseline_n=metrics.baseline_n,
        baseline_total=metrics.baseline_total,
        current_n=metrics.current_n,
        current_total=metrics.current_total,
        baseline_share=metrics.baseline_share,
        current_share=metrics.current_share,
        growth=metrics.growth,
        components=components,
        score=score,
        impact=impact,
        confidence=signal_confidence(
            sample_size=all_current,
            growth_sample_size=metrics.growth_current_total,
            score=score,
            sources_count=len(metrics.source_types),
            trend_corroborated=trend_corroborated,
        ),
        sources_count=len(metrics.source_types),
        source_types=metrics.source_types,
    )
