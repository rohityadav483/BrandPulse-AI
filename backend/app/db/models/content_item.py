import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base
from app.db.models.enums import (
    ContentPurpose,
    DateConfidence,
    SourceType,
    WindowKind,
    pg_enum,
)

_SHA256_HEX = "'^[0-9a-f]{64}$'"


class ContentItemRow(Base):
    """Normalized, dated, deduplicated item from any SerpApi content engine (Phase 3.2).

    docs/DATABASE.md section 5.5. Filled from `raw_items` by `pipeline/process_raw_items.py`.
    `window` is null for investigation items and for collection items dated outside both windows
    (kept, counted in no window). `dup_group` is the hash of the normalized title: items sharing
    it count as one source for independence. `analysis_id` cascades on delete; brands never do.
    """

    __tablename__ = "content_items"
    __table_args__ = (
        CheckConstraint(
            "engine IN ('google', 'google_news', 'google_forums', 'youtube')",
            name="engine_allowed",
        ),
        CheckConstraint("title ~ '\\S'", name="title_not_blank"),
        CheckConstraint("url ~ '\\S'", name="url_not_blank"),
        CheckConstraint("domain ~ '\\S'", name="domain_not_blank"),
        CheckConstraint(f"url_hash ~ {_SHA256_HEX}", name="url_hash_sha256_hex"),
        CheckConstraint(
            f"content_hash ~ {_SHA256_HEX}", name="content_hash_sha256_hex"
        ),
        CheckConstraint(
            f"dup_group IS NULL OR dup_group ~ {_SHA256_HEX}",
            name="dup_group_sha256_hex",
        ),
        # A date exists exactly when its confidence is not 'unknown'.
        CheckConstraint(
            "(date_confidence = 'unknown') = (published_at IS NULL)",
            name="date_matches_confidence",
        ),
        CheckConstraint(
            "purpose <> 'investigation' OR \"window\" IS NULL",
            name="investigation_no_window",
        ),
        # Exact dedupe (DATABASE.md 5.5): one row per normalized text per analysis and brand.
        Index(
            "uq_content_items_identity",
            "analysis_id",
            "brand_id",
            "content_hash",
            unique=True,
        ),
        Index(
            "ix_content_items_analysis_brand_window",
            "analysis_id",
            "brand_id",
            "window",
        ),
        Index("ix_content_items_analysis_source_type", "analysis_id", "source_type"),
        Index(
            "ix_content_items_content_hash", "content_hash"
        ),  # cross-analysis NLP reuse
        Index(
            "ix_content_items_analysis_brand_url_hash",
            "analysis_id",
            "brand_id",
            "url_hash",
        ),
        Index("ix_content_items_analysis_dup_group", "analysis_id", "dup_group"),
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
    window: Mapped[WindowKind | None] = mapped_column(
        pg_enum(WindowKind, "window_kind")
    )
    source_type: Mapped[SourceType] = mapped_column(
        pg_enum(SourceType, "source_type"), nullable=False
    )
    engine: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    url_hash: Mapped[str] = mapped_column(Text, nullable=False)
    domain: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    snippet: Mapped[str | None] = mapped_column(Text)
    author: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    date_confidence: Mapped[DateConfidence] = mapped_column(
        pg_enum(DateConfidence, "date_confidence"), nullable=False
    )
    query: Mapped[str] = mapped_column(Text, nullable=False)
    # `metadata` is reserved on declarative classes, so the attribute differs from the column.
    item_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    content_hash: Mapped[str] = mapped_column(Text, nullable=False)
    dup_group: Mapped[str | None] = mapped_column(Text)
    serp_cache_key: Mapped[str | None] = mapped_column(Text)
    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
