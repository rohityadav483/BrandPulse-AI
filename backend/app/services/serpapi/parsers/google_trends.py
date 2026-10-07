"""Google Trends (`engine=google_trends`, `data_type=TIMESERIES`) -> TrendSeries.

Trends returns an interest-over-time series, not content items, so this parser fills
`ParsedResponse.trends` and leaves `items` empty. Points feed `trend_points` in Phase 5.
"""

from collections.abc import Mapping
from typing import Any

from app.schemas.serp import ParsedResponse, SerpEngine, TrendPoint, TrendSeries
from app.services.serpapi.parsers.common import as_int, text


def _value(entry: Mapping[str, Any]) -> int | None:
    """`extracted_value` is numeric; `value` can be a string such as "<1" (treated as 0)."""
    extracted = entry.get("extracted_value")
    if isinstance(extracted, int) and not isinstance(extracted, bool):
        return extracted
    raw = text(entry.get("value"))
    if raw is None:
        return None
    if raw.startswith("<"):
        return 0
    return as_int(raw)


def parse_google_trends(response: Mapping[str, Any]) -> ParsedResponse:
    block = response.get("interest_over_time")
    block = block if isinstance(block, dict) else {}
    terms: list[str] = []
    points: list[TrendPoint] = []
    skipped = 0

    for row in block.get("timeline_data") or []:
        label = text(row.get("date")) if isinstance(row, dict) else None
        if label is None:
            skipped += 1
            continue
        values: dict[str, int | None] = {}
        for entry in row.get("values") or []:
            term = text(entry.get("query")) if isinstance(entry, dict) else None
            if term is None:
                continue
            if term not in terms:
                terms.append(term)
            values[term] = _value(entry)
        points.append(
            TrendPoint(
                date_raw=label, timestamp=as_int(row.get("timestamp")), values=values
            )
        )

    averages: dict[str, int] = {}
    for entry in block.get("averages") or []:
        term = text(entry.get("query")) if isinstance(entry, dict) else None
        average = _value(entry) if term is not None else None
        if term is not None and average is not None:
            averages[term] = average
            if term not in terms:
                terms.append(term)

    series = TrendSeries(terms=terms, points=points, averages=averages)
    return ParsedResponse(
        engine=SerpEngine.google_trends, trends=series, skipped=skipped
    )
