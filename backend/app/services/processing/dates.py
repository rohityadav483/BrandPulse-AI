"""Publication dates: absolute and relative parsing, `date_confidence`, window assignment.

Pure functions, stdlib only. Honesty rules (docs/ARCHITECTURE.md decision 7):

- `exact`: SerpApi gave an ISO timestamp or a complete calendar date.
- `approximate`: derived ("3 weeks ago", or a date without a year). Relative dates are
  measured from `reference`, the moment the result was collected, not from `as_of_date`.
- `unknown`: missing, unparseable, implausible, or in the future. Never guessed.

Month-first numeric dates (`07/30/2026`) are assumed, as SerpApi emits them. A relative month is
30 days and a relative year 365 days.
"""

import re
from datetime import UTC, date, datetime, timedelta

from pydantic import BaseModel, ConfigDict

from app.schemas.domain import DateConfidence, WindowKind
from app.schemas.serp import WindowSet

MIN_YEAR = 1995
FUTURE_TOLERANCE = timedelta(days=1)  # time zones and clock skew

_UNIT_SECONDS = {
    "second": 1,
    "minute": 60,
    "hour": 3600,
    "day": 86400,
    "week": 7 * 86400,
    "month": 30 * 86400,
    "year": 365 * 86400,
}
_NUMBER_WORDS = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5}
_PREFIX = re.compile(
    r"^(?:streamed|premiered|updated|posted|published|reviewed)\s+", re.IGNORECASE
)
_RELATIVE = re.compile(
    r"^(?P<n>\d+|a|an|one|two|three|four|five)\s*\+?\s*"
    r"(?P<unit>second|minute|hour|day|week|month|year)s?\s+ago$",
    re.IGNORECASE,
)
_SERP_NEWS = re.compile(
    r"^(?P<m>\d{1,2})/(?P<d>\d{1,2})/(?P<y>\d{4}),\s*(?P<h>\d{1,2}):(?P<min>\d{2})\s*"
    r"(?P<ampm>AM|PM)(?:,\s*(?P<sign>[+-])(?P<oh>\d{2})(?P<om>\d{2})(?:\s*UTC)?)?$",
    re.IGNORECASE,
)
_DATE_FORMATS = (
    "%b %d, %Y",
    "%B %d, %Y",
    "%d %b %Y",
    "%d %B %Y",
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%m/%d/%Y",
)
_YEARLESS_FORMATS = ("%b %d", "%B %d", "%d %b", "%d %B")


class ParsedDate(BaseModel):
    """Result of `parse_published`. `published_at` is None exactly when confidence is unknown."""

    model_config = ConfigDict(frozen=True)

    published_at: datetime | None
    confidence: DateConfidence


UNKNOWN = ParsedDate(published_at=None, confidence=DateConfidence.unknown)


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _plausible(moment: datetime, reference: datetime) -> bool:
    return moment.year >= MIN_YEAR and moment <= reference + FUTURE_TOLERANCE


def _parse_iso(value: str) -> datetime | None:
    try:
        return _utc(datetime.fromisoformat(value.strip()))
    except ValueError:
        return None


def _parse_serp_news(value: str) -> datetime | None:
    match = _SERP_NEWS.match(value.strip())
    if match is None:
        return None
    hour = int(match["h"]) % 12 + (12 if match["ampm"].upper() == "PM" else 0)
    try:
        moment = datetime(
            int(match["y"]),
            int(match["m"]),
            int(match["d"]),
            hour,
            int(match["min"]),
            tzinfo=UTC,
        )
    except ValueError:
        return None
    if match["sign"]:
        offset = timedelta(hours=int(match["oh"]), minutes=int(match["om"]))
        moment -= offset if match["sign"] == "+" else -offset
    return moment


def _parse_calendar_date(value: str) -> datetime | None:
    text = re.sub(r"\s+", " ", value.strip().rstrip("."))
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    return None


def _parse_yearless(value: str, reference: datetime) -> datetime | None:
    text = re.sub(r"\s+", " ", value.strip().rstrip("."))
    for fmt in _YEARLESS_FORMATS:
        try:
            parsed = datetime.strptime(f"{text} 2000", f"{fmt} %Y").replace(
                tzinfo=UTC
            )  # 2000: leap year
        except ValueError:
            continue
        for year in (reference.year, reference.year - 1):
            try:
                candidate = parsed.replace(year=year, tzinfo=UTC)
            except ValueError:  # Feb 29 in a non-leap year
                continue
            if candidate <= reference + FUTURE_TOLERANCE:
                return candidate
    return None


def _parse_relative(value: str, reference: datetime) -> datetime | None:
    text = _PREFIX.sub("", value.strip()).strip()
    lowered = text.casefold()
    if lowered in {"just now", "now", "today"}:
        return reference
    if lowered == "yesterday":
        return reference - timedelta(days=1)
    match = _RELATIVE.match(text)
    if match is None:
        return None
    raw = match["n"].casefold()
    count = int(raw) if raw.isdigit() else _NUMBER_WORDS[raw]
    return reference - timedelta(
        seconds=count * _UNIT_SECONDS[match["unit"].casefold()]
    )


def parse_published(
    published_raw: str | None, published_iso: str | None, reference: datetime
) -> ParsedDate:
    """Interpret SerpApi's date strings. `reference` is when the result was collected.

    `published_iso` wins over `published_raw`. Nothing is ever raised or guessed: bad input is
    `unknown`.
    """
    reference = _utc(reference)

    if (
        published_iso
        and (moment := _parse_iso(published_iso)) is not None
        and _plausible(moment, reference)
    ):
        return ParsedDate(published_at=moment, confidence=DateConfidence.exact)

    raw = (published_raw or "").strip()
    if not raw:
        return UNKNOWN

    for parser in (_parse_serp_news, _parse_iso, _parse_calendar_date):
        moment = parser(raw)
        if moment is not None:
            if _plausible(moment, reference):
                return ParsedDate(published_at=moment, confidence=DateConfidence.exact)
            return UNKNOWN

    for approximate in (
        _parse_relative(raw, reference),
        _parse_yearless(raw, reference),
    ):
        if approximate is not None and _plausible(approximate, reference):
            return ParsedDate(
                published_at=approximate, confidence=DateConfidence.approximate
            )
    return UNKNOWN


def window_for_date(published_at: datetime, windows: WindowSet) -> WindowKind | None:
    """`current` or `baseline` if the UTC calendar date falls inside that window (inclusive)."""
    day: date = _utc(published_at).date()
    if windows.current_start <= day <= windows.current_end:
        return WindowKind.current
    if windows.baseline_start <= day <= windows.baseline_end:
        return WindowKind.baseline
    return None


def assign_window(
    parsed: ParsedDate, windows: WindowSet | None, planned: WindowKind | None
) -> WindowKind | None:
    """Window an item counts in.

    - A known date decides: inside a window -> that window, outside both -> None (the item is
      kept but counts in no window, e.g. an old video from an engine with no date filter).
    - No usable date (or no windows given): the window of the planned call that found it.
    """
    if windows is not None and parsed.published_at is not None:
        return window_for_date(parsed.published_at, windows)
    return planned
