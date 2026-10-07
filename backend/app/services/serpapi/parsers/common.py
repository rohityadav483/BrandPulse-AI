"""Helpers shared by every engine parser. Pure functions, no I/O."""

from collections.abc import Mapping
from typing import Any

from app.schemas.serp import SerpEngine

# Result-list keys per content engine, in lookup order. Google Forums key names are not yet
# verified against a live response (docs/SERPAPI_FINDINGS.md), so several are accepted.
RESULT_LIST_KEYS: dict[SerpEngine, tuple[str, ...]] = {
    SerpEngine.google: ("organic_results",),
    SerpEngine.google_news: ("news_results",),
    SerpEngine.google_forums: (
        "organic_results",
        "forum_results",
        "discussions_and_forums",
    ),
    SerpEngine.youtube: ("video_results",),
}


def response_error(response: Mapping[str, Any]) -> str | None:
    """The `error` text of a SerpApi response, if any."""
    error = response.get("error")
    return str(error) if error else None


def is_no_results_error(message: str) -> bool:
    """SerpApi reports an empty search as an error string, e.g. "Google hasn't returned any
    results for this query." That is an empty result, not a failure."""
    return "returned any results" in message.casefold()


def has_results(engine: SerpEngine | str, response: Mapping[str, Any]) -> bool:
    """True if the response carries at least one result row (or Trends timeline point)."""
    engine = SerpEngine(engine)
    if engine is SerpEngine.google_trends:
        block = response.get("interest_over_time")
        return isinstance(block, dict) and bool(block.get("timeline_data"))
    return any(response.get(key) for key in RESULT_LIST_KEYS[engine])


def text(value: Any) -> str | None:
    """Stripped string, or None when missing/blank."""
    if value is None or isinstance(value, bool):
        return None
    cleaned = str(value).strip()
    return cleaned or None


def as_int(value: Any) -> int | None:
    """Int from 1234, "1234", "1,234" or "1,234 views". Abbreviations ("1.2K") give None."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        parts = value.split()
        token = parts[0].replace(",", "") if parts else ""
        return int(token) if token.isdigit() else None
    return None


def compact(**fields: Any) -> dict[str, Any]:
    """Keep only fields that carry a value (metadata stays small and JSON-safe)."""
    return {
        key: value for key, value in fields.items() if value not in (None, "", [], {})
    }


def rows(
    response: Mapping[str, Any], keys: tuple[str, ...]
) -> tuple[list[dict[str, Any]], int]:
    """Dict rows from the first non-empty list under `keys`, plus the count of non-dict rows."""
    for key in keys:
        raw = response.get(key)
        if isinstance(raw, list) and raw:
            good = [row for row in raw if isinstance(row, dict)]
            return good, len(raw) - len(good)
    return [], 0
