"""Deterministic Trends corroboration."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date

# Search interest must rise at least this much (current vs baseline window average) to
# count as moving the same way as a negative-sentiment spike.
CORROBORATION_MIN_CHANGE_PCT = 10.0


def corroborates(values: list[float | int], *, min_points: int = 2) -> bool:
    if len(values) < min_points or values[0] == values[-1]:
        return False
    return values[-1] > values[0]


def _mean(values: list[int | float]) -> float | None:
    return sum(values) / len(values) if values else None


def interest_change_pct(
    points: Iterable[tuple[date, int | float]],
    *,
    baseline: tuple[date, date],
    current: tuple[date, date],
) -> float | None:
    """Percent change of mean search interest, current window vs baseline window.

    `None` when either window has no points or the baseline mean is 0 (no defined ratio).
    """
    rows = list(points)
    base = _mean([v for d, v in rows if baseline[0] <= d <= baseline[1]])
    cur = _mean([v for d, v in rows if current[0] <= d <= current[1]])
    if base is None or cur is None or base == 0:
        return None
    return round((cur - base) / base * 100, 1)


def trend_corroborated(change_pct: float | None) -> bool:
    """Search interest rose meaningfully, i.e. it moved the same way as the spike."""
    return change_pct is not None and change_pct >= CORROBORATION_MIN_CHANGE_PCT
