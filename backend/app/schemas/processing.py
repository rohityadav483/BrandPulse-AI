"""Phase 3.2 value types: the normalized `ContentItem` and the processing report.

Pure Pydantic (no DB, no I/O), shared by `services/processing`, `db/repositories/content_item`
and `pipeline/`. `ContentItem` is the output of `RawItem -> ContentItem` (ARCHITECTURE.md
section 5); `StoredContentItem` is a persisted `content_items` row (DATABASE.md section 5.5).
"""

import enum
from datetime import datetime
from typing import Any, Self
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.schemas.domain import ContentPurpose, DateConfidence, SourceType, WindowKind
from app.schemas.serp import SerpEngine


class ContentItem(BaseModel):
    """A cleaned, canonicalised, dated item. `url` is the canonical URL.

    `window` is None for investigation items, and for collection items whose known date lies
    outside both windows (kept, but counted in no window). `published_at` is None exactly when
    `date_confidence` is `unknown`.
    """

    purpose: ContentPurpose
    window: WindowKind | None = None
    source_type: SourceType
    engine: SerpEngine
    url: str
    url_hash: str
    domain: str
    title: str
    snippet: str | None = None
    author: str | None = None
    published_at: datetime | None = None
    date_confidence: DateConfidence
    query: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    content_hash: str
    dup_group: str | None = None
    serp_cache_key: str | None = None
    collected_at: datetime

    @model_validator(mode="after")
    def _date_matches_confidence(self) -> Self:
        if (self.published_at is None) != (
            self.date_confidence is DateConfidence.unknown
        ):
            raise ValueError(
                "published_at is None exactly when date_confidence is unknown"
            )
        if self.purpose is ContentPurpose.investigation and self.window is not None:
            raise ValueError("investigation items have no window")
        return self


class StoredContentItem(ContentItem):
    """A persisted `content_items` row."""

    id: UUID
    analysis_id: UUID
    brand_id: UUID


class ContentWriteResult(BaseModel):
    """Outcome of persisting a batch: rows created vs. skipped by the unique content hash."""

    inserted: int
    duplicates: int
    inserted_ids: list[UUID] = Field(default_factory=list)


class DropReason(enum.StrEnum):
    empty_title = "empty_title"  # nothing readable left after cleaning
    invalid_url = "invalid_url"  # not an http(s) URL with a host
    duplicate_content_hash = "duplicate_content_hash"  # same normalized title + snippet
    duplicate_url = "duplicate_url"  # same canonical URL
    already_stored = (
        "already_stored"  # hash already in content_items for this analysis + brand
    )


class DroppedRaw(BaseModel):
    """A raw item that did not become a content item, with the reason (never silent)."""

    raw_item_id: UUID
    reason: DropReason


class ProcessingStats(BaseModel):
    raw_in: int = 0
    kept: int = 0
    dropped: int = 0
    near_duplicate_groups: int = (
        0  # groups of kept items that share a dup_group (size >= 2)
    )
    date_exact: int = 0
    date_approximate: int = 0
    date_unknown: int = 0
    window_current: int = 0
    window_baseline: int = 0
    window_none: int = 0


class ProcessingOutcome(BaseModel):
    """Pure result of processing one (analysis, brand) batch of raw items."""

    items: list[ContentItem] = Field(default_factory=list)
    dropped: list[DroppedRaw] = Field(default_factory=list)
    stats: ProcessingStats = Field(default_factory=ProcessingStats)


class ProcessingRunResult(BaseModel):
    """What the pipeline stage reports after reading `raw_items` and writing `content_items`."""

    analysis_id: UUID
    raw_read: int = 0
    kept: int = 0
    inserted: int = 0
    db_duplicates: int = (
        0  # kept items the unique index still skipped (concurrent re-run)
    )
    dropped: list[DroppedRaw] = Field(default_factory=list)
    stats: ProcessingStats = Field(default_factory=ProcessingStats)

    def dropped_by_reason(self) -> dict[DropReason, int]:
        counts: dict[DropReason, int] = {}
        for drop in self.dropped:
            counts[drop.reason] = counts.get(drop.reason, 0) + 1
        return counts
