"""Deterministic Phase 5 window metrics."""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass

from app.config.scoring_config import clamp, growth_ratio

GROWTH_SOURCES = frozenset({"web", "news"})
ALL_SOURCES = frozenset({"web", "news", "youtube", "forum", "shopping"})


@dataclass(frozen=True)
class MetricItem:
    """Minimal item contract consumed by the metrics layer."""

    window: str
    source_type: str
    aspect: str
    sentiment: str
    negative_prob: float
    is_about_brand: bool = True
    growth_eligible: bool = True
    item_id: str | None = None


@dataclass(frozen=True)
class WindowMetrics:
    current_n: int
    current_total: int
    baseline_n: int
    baseline_total: int
    current_share: float
    baseline_share: float
    growth: float | None
    frequency: float
    cross_source: float
    sentiment_impact: float
    source_types: tuple[str, ...]
    growth_current_total: int
    growth_baseline_total: int


def _items(items: Iterable[MetricItem], aspect: str) -> list[MetricItem]:
    return [x for x in items if x.is_about_brand and x.aspect == aspect]


def _share(n: int, total: int) -> float:
    return n / total if total else 0.0


def compute_window_metrics(items: Iterable[MetricItem], aspect: str) -> WindowMetrics:
    """Compute all Phase 5 metrics for one aspect without I/O or mutation."""
    all_rows = [x for x in items if x.is_about_brand]
    rows = [x for x in all_rows if x.aspect == aspect]
    current = [x for x in rows if x.window == "current"]
    baseline = [x for x in rows if x.window == "baseline"]
    all_current = [x for x in all_rows if x.window == "current"]
    current_item_ids = {x.item_id for x in all_current if x.item_id is not None}
    current_denominator = (
        len(current_item_ids) if current_item_ids else len(all_current)
    )

    cur_growth = [
        x for x in current if x.growth_eligible and x.source_type in GROWTH_SOURCES
    ]
    base_growth = [
        x for x in baseline if x.growth_eligible and x.source_type in GROWTH_SOURCES
    ]
    cur_n = sum(x.sentiment == "negative" for x in cur_growth)
    base_n = sum(x.sentiment == "negative" for x in base_growth)
    cur_total = len(cur_growth)
    base_total = len(base_growth)
    current_share = _share(cur_n, cur_total)
    baseline_share = _share(base_n, base_total)
    growth = (
        growth_ratio(cur_n, cur_total, base_n, base_total)
        if cur_total and base_total
        else None
    )

    negative_current = [x for x in current if x.sentiment == "negative"]
    negative_item_ids = {x.item_id for x in negative_current if x.item_id is not None}
    negative_count = (
        len(negative_item_ids) if negative_item_ids else len(negative_current)
    )
    frequency = _share(negative_count, current_denominator)
    source_types = tuple(sorted({x.source_type for x in negative_current}))
    cross_source = clamp(len(source_types) / 4.0)
    probs = [
        x.negative_prob for x in negative_current if math.isfinite(x.negative_prob)
    ]
    sentiment_impact = sum(probs) / len(probs) if probs else 0.0

    return WindowMetrics(
        current_n=cur_n,
        current_total=cur_total,
        baseline_n=base_n,
        baseline_total=base_total,
        current_share=current_share,
        baseline_share=baseline_share,
        growth=growth,
        frequency=frequency,
        cross_source=cross_source,
        sentiment_impact=clamp(sentiment_impact),
        source_types=source_types,
        growth_current_total=cur_total,
        growth_baseline_total=base_total,
    )
