"""Engine parsers: raw SerpApi JSON -> `RawItem[]` (or a `TrendSeries` for Google Trends).

Parsers are pure and defensive: a malformed row is skipped and counted, never raised.
"""

from collections.abc import Callable, Mapping
from typing import Any

from app.schemas.serp import ParsedResponse, QuerySpec, SerpEngine
from app.services.serpapi.parsers.google_forums import parse_google_forums
from app.services.serpapi.parsers.google_news import parse_google_news
from app.services.serpapi.parsers.google_trends import parse_google_trends
from app.services.serpapi.parsers.google_web import parse_google_web
from app.services.serpapi.parsers.youtube import parse_youtube

PARSERS: dict[SerpEngine, Callable[[Mapping[str, Any]], ParsedResponse]] = {
    SerpEngine.google: parse_google_web,
    SerpEngine.google_news: parse_google_news,
    SerpEngine.google_forums: parse_google_forums,
    SerpEngine.youtube: parse_youtube,
    SerpEngine.google_trends: parse_google_trends,
}


def parse_response(
    spec: QuerySpec,
    response: Mapping[str, Any],
    cache_key: str | None = None,
) -> ParsedResponse:
    """Parse `response` with the parser for `spec.engine`.

    Every item is stamped with the query text and the cache key it came from, so processing
    can trace an item back to its raw response (`content_items.query`, `serp_cache_key`).
    """
    parsed = PARSERS[spec.engine](response)
    if not parsed.items:
        return parsed
    stamped = [
        item.model_copy(update={"query": spec.query, "serp_cache_key": cache_key})
        for item in parsed.items
    ]
    return parsed.model_copy(update={"items": stamped})


__all__ = ["PARSERS", "parse_response"]
