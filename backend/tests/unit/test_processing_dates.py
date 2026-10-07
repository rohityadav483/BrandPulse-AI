"""dates: absolute + relative parsing, date_confidence, window assignment. Pure, table-driven."""

from datetime import UTC, date, datetime, timedelta, timezone

import pytest

from app.schemas.domain import DateConfidence, WindowKind
from app.schemas.serp import WindowSet
from app.services.processing.dates import (
    UNKNOWN,
    ParsedDate,
    assign_window,
    parse_published,
    window_for_date,
)

REF = datetime(2026, 8, 10, 12, 0, tzinfo=UTC)
WINDOWS = WindowSet(
    as_of_date=date(2026, 8, 10),
    period_days=30,
    current_start=date(2026, 7, 12),
    current_end=date(2026, 8, 10),
    baseline_start=date(2026, 6, 12),
    baseline_end=date(2026, 7, 11),
)
EXACT, APPROX, UNK = DateConfidence.exact, DateConfidence.approximate, DateConfidence.unknown


def at(*args) -> datetime:
    return datetime(*args, tzinfo=UTC)


@pytest.mark.parametrize(
    ("raw", "iso", "expected_at", "confidence"),
    [
        # exact: ISO wins, even over a different raw string
        (None, "2026-07-30T07:00:00Z", at(2026, 7, 30, 7), EXACT),
        ("3 weeks ago", "2026-07-30T07:00:00Z", at(2026, 7, 30, 7), EXACT),
        (None, "2026-07-30T09:00:00+02:00", at(2026, 7, 30, 7), EXACT),
        (None, "2026-07-30", at(2026, 7, 30), EXACT),
        # exact: SerpApi news format, with and without offset
        ("07/30/2026, 07:00 AM, +0000 UTC", None, at(2026, 7, 30, 7), EXACT),
        ("08/02/2026, 10:15 AM, +0000 UTC", None, at(2026, 8, 2, 10, 15), EXACT),
        ("07/21/2026, 03:40 PM, +0000 UTC", None, at(2026, 7, 21, 15, 40), EXACT),
        ("07/30/2026, 12:00 AM, +0000 UTC", None, at(2026, 7, 30, 0), EXACT),
        ("07/30/2026, 12:30 PM", None, at(2026, 7, 30, 12, 30), EXACT),
        ("07/30/2026, 09:00 AM, +0200 UTC", None, at(2026, 7, 30, 7), EXACT),
        ("07/30/2026, 09:00 AM, -0500 UTC", None, at(2026, 7, 30, 14), EXACT),
        # exact: calendar dates
        ("Jul 29, 2026", None, at(2026, 7, 29), EXACT),
        ("July 29, 2026", None, at(2026, 7, 29), EXACT),
        ("29 Jul 2026", None, at(2026, 7, 29), EXACT),
        ("2026-07-29", None, at(2026, 7, 29), EXACT),
        ("07/29/2026", None, at(2026, 7, 29), EXACT),
        # approximate: relative, measured from the collection moment
        ("3 weeks ago", None, REF - timedelta(weeks=3), APPROX),
        ("2 weeks ago", None, REF - timedelta(weeks=2), APPROX),
        ("1 month ago", None, REF - timedelta(days=30), APPROX),
        ("2 months ago", None, REF - timedelta(days=60), APPROX),
        ("1 year ago", None, REF - timedelta(days=365), APPROX),
        ("5 days ago", None, REF - timedelta(days=5), APPROX),
        ("3 hours ago", None, REF - timedelta(hours=3), APPROX),
        ("45 minutes ago", None, REF - timedelta(minutes=45), APPROX),
        ("a day ago", None, REF - timedelta(days=1), APPROX),
        ("an hour ago", None, REF - timedelta(hours=1), APPROX),
        ("one week ago", None, REF - timedelta(weeks=1), APPROX),
        ("3 WEEKS AGO", None, REF - timedelta(weeks=3), APPROX),
        ("Streamed 2 days ago", None, REF - timedelta(days=2), APPROX),
        ("Premiered 1 week ago", None, REF - timedelta(weeks=1), APPROX),
        ("yesterday", None, REF - timedelta(days=1), APPROX),
        ("today", None, REF, APPROX),
        ("just now", None, REF, APPROX),
        # approximate: no year -> latest past occurrence
        ("Aug 3", None, at(2026, 8, 3), APPROX),
        ("Dec 25", None, at(2025, 12, 25), APPROX),
        ("3 Aug", None, at(2026, 8, 3), APPROX),
    ],
)
def test_parse_published(raw, iso, expected_at, confidence):
    parsed = parse_published(raw, iso, REF)
    assert parsed.published_at == expected_at
    assert parsed.confidence is confidence


@pytest.mark.parametrize(
    ("raw", "iso"),
    [
        (None, None),
        ("", None),
        ("   ", None),
        ("garbage", None),
        ("sometime last week", None),
        ("soon", None),
        ("0 weeks", None),
        ("13/45/2026", None),
        ("02/30/2026, 07:00 AM, +0000 UTC", None),  # impossible date
        ("Dec 25, 2030", None),  # in the future
        ("1990-01-01", None),  # implausibly old
        ("in 3 days", None),
        (None, "not-an-iso"),
        (None, "2030-01-01T00:00:00Z"),
    ],
)
def test_unparseable_or_implausible_dates_are_unknown_never_guessed(raw, iso):
    parsed = parse_published(raw, iso, REF)
    assert parsed == UNKNOWN
    assert parsed.published_at is None and parsed.confidence is UNK


def test_bad_iso_falls_back_to_a_usable_raw_string():
    parsed = parse_published("Jul 29, 2026", "not-an-iso", REF)
    assert parsed.published_at == at(2026, 7, 29) and parsed.confidence is EXACT


def test_future_iso_falls_back_to_raw_relative():
    parsed = parse_published("2 days ago", "2030-01-01T00:00:00Z", REF)
    assert parsed.confidence is APPROX


def test_small_future_skew_is_tolerated():
    parsed = parse_published(None, (REF + timedelta(hours=5)).isoformat(), REF)
    assert parsed.confidence is EXACT


def test_naive_reference_is_treated_as_utc():
    parsed = parse_published("1 day ago", None, datetime(2026, 8, 10, 12))
    assert parsed.published_at == REF - timedelta(days=1)


def test_relative_dates_follow_the_reference_not_the_calendar():
    later = REF + timedelta(days=30)
    assert parse_published("3 weeks ago", None, later).published_at == later - timedelta(weeks=3)


def test_feb_29_without_year_is_unknown_when_neither_candidate_year_is_a_leap_year():
    assert parse_published("Feb 29", None, REF) == UNKNOWN


def test_parsed_date_is_frozen():
    parsed = ParsedDate(published_at=None, confidence=UNK)
    with pytest.raises(Exception):  # noqa: B017 - pydantic ValidationError
        parsed.confidence = EXACT


# ---------- windows ----------


@pytest.mark.parametrize(
    ("moment", "window"),
    [
        (at(2026, 7, 12), WindowKind.current),  # first day of current
        (at(2026, 8, 10, 23, 59), WindowKind.current),  # last day, late in the day
        (at(2026, 7, 30, 7), WindowKind.current),
        (at(2026, 7, 11, 23, 59), WindowKind.baseline),  # last day of baseline
        (at(2026, 6, 12), WindowKind.baseline),  # first day of baseline
        (at(2026, 6, 11, 23, 59), None),  # day before baseline
        (at(2026, 8, 11), None),  # day after current
        (at(2025, 1, 1), None),
    ],
)
def test_window_for_date(moment, window):
    assert window_for_date(moment, WINDOWS) is window


def test_window_uses_the_utc_calendar_date():
    # 00:30 on Jul 12 at UTC+14 is still Jul 11 in UTC -> baseline, not current
    local = datetime(2026, 7, 12, 0, 30, tzinfo=timezone(timedelta(hours=14)))
    assert window_for_date(local, WINDOWS) is WindowKind.baseline


@pytest.mark.parametrize(
    ("parsed_at", "planned", "expected"),
    [
        (at(2026, 7, 30), WindowKind.baseline, WindowKind.current),  # the date decides
        (at(2026, 7, 1), WindowKind.current, WindowKind.baseline),
        (at(2025, 1, 1), WindowKind.current, None),  # dated outside both windows
        (None, WindowKind.current, WindowKind.current),  # undated -> planned window
        (None, WindowKind.baseline, WindowKind.baseline),
        (None, None, None),
    ],
)
def test_assign_window(parsed_at, planned, expected):
    parsed = ParsedDate(published_at=parsed_at, confidence=EXACT if parsed_at else UNK)
    assert assign_window(parsed, WINDOWS, planned) is expected


def test_assign_window_without_windows_uses_the_planned_window():
    parsed = ParsedDate(published_at=at(2026, 7, 30), confidence=EXACT)
    assert assign_window(parsed, None, WindowKind.baseline) is WindowKind.baseline
