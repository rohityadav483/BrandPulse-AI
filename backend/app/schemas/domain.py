"""Shared API vocabulary: enums mirroring docs/DATABASE.md section 3, plus tiny pure helpers.

Pure Python (no DB, no I/O). `app/schemas/api.py` builds the HTTP DTOs on top of these.
Values are lowercase strings, exactly as in the DB enums, so API and DB cannot drift.
"""

import enum


class AnalysisStatus(enum.StrEnum):
    queued = "queued"
    running = "running"
    completed = "completed"
    partial = "partial"
    failed = "failed"


class AnalysisStage(enum.StrEnum):
    planning = "planning"
    collecting = "collecting"
    processing = "processing"
    analyzing = "analyzing"
    detecting = "detecting"
    snapshotting = "snapshotting"
    done = "done"


class BrandRole(enum.StrEnum):
    target = "target"
    competitor = "competitor"
    suggested = "suggested"


class SourceType(enum.StrEnum):
    web = "web"
    news = "news"
    youtube = "youtube"
    forum = "forum"
    shopping = "shopping"


class WindowKind(enum.StrEnum):
    baseline = "baseline"
    current = "current"


class ContentPurpose(enum.StrEnum):
    collection = "collection"
    investigation = "investigation"


class DateConfidence(enum.StrEnum):
    exact = "exact"
    approximate = "approximate"
    unknown = "unknown"


class Sentiment(enum.StrEnum):
    positive = "positive"
    neutral = "neutral"
    negative = "negative"


class SignalKind(enum.StrEnum):
    aspect_negative_spike = (
        "aspect_negative_spike"  # `topic_surge` is reserved, not in the MVP
    )


class ImpactLevel(enum.StrEnum):
    low = "low"
    medium = "medium"
    high = "high"


class SignalStatus(enum.StrEnum):
    detected = "detected"
    investigating = "investigating"
    investigated = "investigated"


class InvestigationStatus(enum.StrEnum):
    queued = "queued"
    running = "running"
    completed = "completed"
    failed = "failed"


class InvestigationStep(enum.StrEnum):
    generating_queries = "generating_queries"
    collecting_evidence = "collecting_evidence"
    scoring_evidence = "scoring_evidence"
    comparing_competitors = "comparing_competitors"
    synthesizing = "synthesizing"
    recommending = "recommending"
    done = "done"


class ScopeVerdict(enum.StrEnum):
    brand_specific = "brand_specific"
    industry_wide = "industry_wide"
    inconclusive = "inconclusive"
    unknown = "unknown"


class Stance(enum.StrEnum):
    supports = "supports"
    contradicts = "contradicts"
    neutral = "neutral"


class Priority(enum.StrEnum):
    low = "low"
    medium = "medium"
    high = "high"


# --- API-only vocabulary (not Postgres enums) -------------------------------------------------


class ConfidenceLabel(enum.StrEnum):
    """Derived at read time from the 0-100 score (DATABASE.md section 3)."""

    low = "low"
    medium = "medium"
    high = "high"


class ConfidenceSource(enum.StrEnum):
    """API.md section 3.4: which number `confidence` currently reflects."""

    signal = "signal"
    investigation = "investigation"


class GeneratedBy(enum.StrEnum):
    """API.md section 3.8: `fallback` = deterministic templates because Groq was unavailable."""

    llm = "llm"
    fallback = "fallback"


class Category(enum.StrEnum):
    """Aspect lexicon preset (API.md section 3.1)."""

    consumer_electronics = "consumer_electronics"
    generic = "generic"


class StepState(enum.StrEnum):
    """State of one investigation step (API.md section 3.8)."""

    done = "done"
    active = "active"
    pending = "pending"


class BlockedReason(enum.StrEnum):
    """`estimateAnalysis.blocked_reason` (API.md section 3.11)."""

    serpapi_quota_low = "serpapi_quota_low"
    live_data_disabled = "live_data_disabled"
    daily_limit_reached = "daily_limit_reached"


class CoverageSourceType(enum.StrEnum):
    """`source_coverage` entries: the source types plus `trends` (API.md section 3.8)."""

    web = "web"
    news = "news"
    youtube = "youtube"
    forum = "forum"
    shopping = "shopping"
    trends = "trends"


# Known warning codes (API.md section 2). `Warning.code` stays a free string so new codes are
# additive within /api/v1; this tuple is the documented set.
KNOWN_WARNING_CODES: tuple[str, ...] = (
    "serpapi_engine_failed",
    "serpapi_budget_exhausted",
    "low_data",
    "date_coverage_low",
    "llm_step_failed",
    "competitor_data_thin",
    "live_data_disabled",
)

MAX_COMPETITORS = 2
MAX_NAME_LENGTH = 80
PERIOD_DAYS_CHOICES = (7, 14, 30)


def confidence_label(score: float) -> ConfidenceLabel:
    """low < 40, medium 40-69, high >= 70."""
    if score < 40:
        return ConfidenceLabel.low
    if score < 70:
        return ConfidenceLabel.medium
    return ConfidenceLabel.high
