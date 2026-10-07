"""Deterministic Brand Health helpers."""

from __future__ import annotations

from dataclasses import dataclass

from app.config.scoring_config import clamp, health_score

FORMULA_VERSION = "v1"


@dataclass(frozen=True)
class HealthComponents:
    sentiment: int
    engagement: int
    risk: int
    trend: int
    overall: int
    formula_version: str = FORMULA_VERSION


def sentiment_health(positive_pct: float, negative_pct: float) -> int:
    return round(clamp((positive_pct - negative_pct + 100.0) / 2.0) * 100)


def engagement_proxy(current_sample: int, baseline_sample: int) -> int:
    if baseline_sample <= 0:
        return 50 if current_sample else 0
    ratio = current_sample / baseline_sample
    return round(clamp(0.5 + (ratio - 1.0) * 0.5) * 100)


def risk_health(negative_pct: float) -> int:
    return round(clamp(1.0 - negative_pct / 100.0) * 100)


def trend_health(interest_change_pct: float | None) -> int:
    if interest_change_pct is None:
        return 50
    return round(clamp(0.5 + interest_change_pct / 100.0 * 0.5) * 100)


def compute_health(
    *,
    positive_pct: float,
    negative_pct: float,
    current_sample: int,
    baseline_sample: int,
    interest_change_pct: float | None,
) -> HealthComponents:
    sentiment = sentiment_health(positive_pct, negative_pct)
    engagement = engagement_proxy(current_sample, baseline_sample)
    risk = risk_health(negative_pct)
    trend = trend_health(interest_change_pct)
    return HealthComponents(
        sentiment,
        engagement,
        risk,
        trend,
        health_score(sentiment, engagement, risk, trend),
    )
