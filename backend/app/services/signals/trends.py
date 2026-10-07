"""Deterministic Trends corroboration."""

from __future__ import annotations


def corroborates(values: list[float | int], *, min_points: int = 2) -> bool:
    if len(values) < min_points or values[0] == values[-1]:
        return False
    return values[-1] > values[0]
