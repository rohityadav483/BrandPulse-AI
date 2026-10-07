"""SerpApi-layer value types shared by `services/serpapi`, repositories and the pipeline.

Pure Pydantic (no DB, no I/O). Kept out of `schemas/api.py` on purpose: nothing here is an HTTP
DTO. The pipeline maps `SerpEstimate` onto `EstimateAnalysisResponse` (API.md section 3.11) and
`QuotaSnapshot` onto `UsageResponse.serpapi` (API.md section 3.12).
"""

import enum
import hashlib
import json
from datetime import date, datetime
from typing import Any, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.domain import BlockedReason, BrandRole, ContentPurpose, SourceType, WindowKind

ParamValue = str | int | float | bool


class SerpEngine(enum.StrEnum):
    """SerpApi `engine` values used by BrandPulse (ARCHITECTURE.md section 6)."""

    google = "google"
    google_news = "google_news"
    google_forums = "google_forums"
    youtube = "youtube"
    google_trends = "google_trends"


# Trends returns a time series, not content items, so it has no `SourceType`.
ENGINE_SOURCE_TYPE: dict[SerpEngine, SourceType | None] = {
    SerpEngine.google: SourceType.web,
    SerpEngine.google_news: SourceType.news,
    SerpEngine.google_forums: SourceType.forum,
    SerpEngine.youtube: SourceType.youtube,
    SerpEngine.google_trends: None,
}


class UsagePurpose(enum.StrEnum):
    """`serp_usage.purpose` values (DATABASE.md section 5.15)."""

    analysis = "analysis"
    investigation = "investigation"
    fixture_recording = "fixture_recording"
    probe = "probe"


class QuerySpec(BaseModel):
    """One SerpApi request: engine + params. Never holds the API key."""

    model_config = ConfigDict(frozen=True)

    engine: SerpEngine
    params: dict[str, ParamValue]

    @property
    def query(self) -> str:
        key = "search_query" if self.engine is SerpEngine.youtube else "q"
        return str(self.params.get(key, ""))


class WindowSet(BaseModel):
    """Current and baseline windows derived from `as_of_date` (ARCHITECTURE.md section 5.3)."""

    model_config = ConfigDict(frozen=True)

    as_of_date: date
    period_days: int
    current_start: date
    current_end: date
    baseline_start: date
    baseline_end: date


class PlannedCall(BaseModel):
    """One line of a collection plan: the request plus why it is made."""

    model_config = ConfigDict(frozen=True)

    spec: QuerySpec
    brand: str
    role: BrandRole
    window: WindowKind | None = None  # None: one call spans both windows (Trends)

    @property
    def label(self) -> str:
        return f"{self.spec.engine}:{self.role}:{self.brand}:{self.window or 'all'}"


class SerpPlan(BaseModel):
    """Ordered calls (highest priority first). `dropped` = calls cut to fit the call cap."""

    model_config = ConfigDict(frozen=True)

    windows: WindowSet
    calls: list[PlannedCall]
    dropped: list[PlannedCall] = Field(default_factory=list)

    @property
    def planned_calls(self) -> int:
        return len(self.calls)


class RawItem(BaseModel):
    """Canonical item from any content engine (web, news, forums, YouTube). Input to Phase 3.2.

    This is THE contract between `services/serpapi/parsers` and `processing/`. Parsers do no
    cleaning, URL canonicalisation or date parsing: every string is exactly what SerpApi
    returned (`published_raw` is "3 weeks ago", "07/30/2026, 07:00 AM, +0000 UTC"). Cleaning,
    canonical URLs, hashes, date parsing and dedupe are Phase 3.2 work on `RawItem -> ContentItem`.

    Invariants (checked on construction): `engine` is a content engine (not Trends),
    `source_type` is the one `ENGINE_SOURCE_TYPE` assigns to that engine, `title` and `url` are
    not blank. Values are never modified by validation.
    """

    source_type: SourceType
    engine: SerpEngine
    title: str
    url: str
    snippet: str | None = None
    author: str | None = None
    published_raw: str | None = None
    published_iso: str | None = None
    position: int | None = Field(default=None, ge=1)
    query: str | None = None
    serp_cache_key: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("title", "url")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value

    @model_validator(mode="after")
    def _engine_matches_source_type(self) -> Self:
        expected = ENGINE_SOURCE_TYPE[self.engine]
        if expected is None:
            raise ValueError(f"engine {self.engine.value!r} does not produce RawItems")
        if self.source_type is not expected:
            raise ValueError(
                f"engine {self.engine.value!r} yields source_type {expected.value!r}, "
                f"got {self.source_type.value!r}"
            )
        return self

    def compute_raw_key(self) -> str:
        """Exact-occurrence key: sha256 hex over the verbatim identifying fields.

        Idempotency key for persistence, NOT a deduplication key. It deliberately does no
        normalisation (no case folding, no URL canonicalisation, no whitespace cleanup): two
        items get the same key only if SerpApi returned the same occurrence (same engine, query,
        cached response, position, URL, title, snippet and dates). Re-persisting the same parsed
        response is therefore a no-op, while the same article found by two queries stays as two
        raw rows for Phase 3.2 to merge. `author` and `metadata` are not part of the key.
        """
        payload = json.dumps(
            [
                self.engine.value,
                self.source_type.value,
                self.query,
                self.serp_cache_key,
                self.position,
                self.url,
                self.title,
                self.snippet,
                self.published_raw,
                self.published_iso,
            ],
            ensure_ascii=False,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class RawItemContext(BaseModel):
    """Where a batch of RawItems was collected: which analysis, brand, purpose and window.

    Shared by every item of one parsed SerpApi response (a planned call has exactly one brand
    and one window). Mirrors the rule in DATABASE.md section 5.5: `window` is null for
    investigation items and set for collection items.
    """

    model_config = ConfigDict(frozen=True)

    analysis_id: UUID
    brand_id: UUID
    purpose: ContentPurpose = ContentPurpose.collection
    window: WindowKind | None = None
    collected_at: datetime | None = None  # None: the database stamps `now()`

    @model_validator(mode="after")
    def _window_matches_purpose(self) -> Self:
        if self.purpose is ContentPurpose.collection and self.window is None:
            raise ValueError("collection items need a window (baseline or current)")
        if self.purpose is ContentPurpose.investigation and self.window is not None:
            raise ValueError("investigation items have no window")
        return self


class StoredRawItem(RawItem):
    """A persisted `raw_items` row: the RawItem plus its identity and collection context."""

    id: UUID
    analysis_id: UUID
    brand_id: UUID
    purpose: ContentPurpose
    window: WindowKind | None = None
    raw_key: str
    collected_at: datetime


class RawItemWriteResult(BaseModel):
    """Outcome of persisting a batch: rows created vs. skipped as exact repeats."""

    inserted: int
    duplicates: int
    inserted_ids: list[UUID] = Field(default_factory=list)

    @property
    def total(self) -> int:
        return self.inserted + self.duplicates


class TrendPoint(BaseModel):
    date_raw: str
    timestamp: int | None = None
    values: dict[str, int | None]


class TrendSeries(BaseModel):
    """Google Trends interest over time (feeds `trend_points` in Phase 5)."""

    terms: list[str]
    points: list[TrendPoint]
    averages: dict[str, int] = Field(default_factory=dict)


class ParsedResponse(BaseModel):
    """Parser output. Content engines fill `items`; Trends fills `trends`."""

    engine: SerpEngine
    items: list[RawItem] = Field(default_factory=list)
    trends: TrendSeries | None = None
    skipped: int = 0  # result rows dropped for a missing title or URL

    @property
    def is_empty(self) -> bool:
        return not self.items and (self.trends is None or not self.trends.points)


class CacheEntry(BaseModel):
    """A `serp_cache` row (DATABASE.md section 5.4)."""

    cache_key: str
    engine: str
    params: dict[str, ParamValue]
    response: dict[str, Any]
    http_status: int | None = 200
    fetched_at: datetime
    expires_at: datetime
    pinned: bool = False


class UsageRecord(BaseModel):
    """A `serp_usage` row (DATABASE.md section 5.15)."""

    cache_key: str
    engine: str
    cache_hit: bool
    credits: int
    http_status: int | None = None
    analysis_id: UUID | None = None
    investigation_id: UUID | None = None
    purpose: UsagePurpose
    account_label: str
    created_at: datetime


class QuotaSnapshot(BaseModel):
    """Monthly SerpApi counter for the current account label (API.md section 3.12)."""

    month: str  # "YYYY-MM"
    limit: int
    used: int
    remaining: int
    reserve: int
    live_enabled: bool


class SerpEstimate(BaseModel):
    """Result of estimating a plan without calling anything (API.md section 3.11)."""

    windows: WindowSet
    planned_calls: int
    cached_calls: int
    estimated_new_calls: int
    quota: QuotaSnapshot
    live_enabled: bool
    needs_access_code: bool
    can_run: bool
    blocked_reason: BlockedReason | None = None
    new_calls: list[PlannedCall] = Field(default_factory=list)
    cached: list[PlannedCall] = Field(default_factory=list)
