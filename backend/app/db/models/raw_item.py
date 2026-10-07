import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    SmallInteger,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base
from app.db.models.enums import ContentPurpose, SourceType, WindowKind, pg_enum


class RawItemRow(Base):
    """One parsed SerpApi result, stored exactly as the parser returned it (Phase 3.1).

    Staging store between `services/serpapi/parsers` and Phase 3.2 `processing/`. Nothing here is
    cleaned, canonicalised, date-parsed or deduplicated; `content_items` (docs/DATABASE.md
    section 5.5) is the normalized store that Phase 3.2 fills from these rows. See section 5.4a.

    `analysis_id` cascades on delete (children of an analysis go with it, DATABASE.md section 8);
    brands are never cascade-deleted. `serp_cache_key` is a trace pointer with no foreign key:
    cache rows expire and are purged, raw items must outlive them.
    """

    __tablename__ = "raw_items"
    __table_args__ = (
        CheckConstraint(
            "engine IN ('google', 'google_news', 'google_forums', 'youtube')",
            name="engine_allowed",
        ),
        CheckConstraint("title ~ '\\S'", name="title_not_blank"),
        CheckConstraint("url ~ '\\S'", name="url_not_blank"),
        CheckConstraint("position IS NULL OR position >= 1", name="position_positive"),
        CheckConstraint("raw_key ~ '^[0-9a-f]{64}$'", name="raw_key_sha256_hex"),
        CheckConstraint(
            "(purpose = 'collection' AND \"window\" IS NOT NULL) "
            "OR (purpose = 'investigation' AND \"window\" IS NULL)",
            name="purpose_window_consistent",
        ),
        # Idempotency: the same occurrence is stored once per (analysis, brand, purpose).
        Index(
            "uq_raw_items_identity", "analysis_id", "brand_id", "purpose", "raw_key", unique=True
        ),
        Index("ix_raw_items_analysis_brand_window", "analysis_id", "brand_id", "window"),
        Index("ix_raw_items_analysis_source_type", "analysis_id", "source_type"),
        Index("ix_raw_items_serp_cache_key", "serp_cache_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    analysis_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("analyses.id", ondelete="CASCADE"), nullable=False
    )
    brand_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("brands.id"), nullable=False)
    purpose: Mapped[ContentPurpose] = mapped_column(
        pg_enum(ContentPurpose, "content_purpose"), nullable=False
    )
    window: Mapped[WindowKind | None] = mapped_column(pg_enum(WindowKind, "window_kind"))
    source_type: Mapped[SourceType] = mapped_column(
        pg_enum(SourceType, "source_type"), nullable=False
    )
    engine: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    snippet: Mapped[str | None] = mapped_column(Text)
    author: Mapped[str | None] = mapped_column(Text)
    published_raw: Mapped[str | None] = mapped_column(Text)
    published_iso: Mapped[str | None] = mapped_column(Text)
    position: Mapped[int | None] = mapped_column(SmallInteger)
    query: Mapped[str | None] = mapped_column(Text)
    serp_cache_key: Mapped[str | None] = mapped_column(Text)
    # `metadata` is reserved on declarative classes, so the attribute differs from the column.
    item_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    raw_key: Mapped[str] = mapped_column(Text, nullable=False)
    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
