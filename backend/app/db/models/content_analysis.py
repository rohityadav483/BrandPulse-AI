import uuid
from datetime import datetime

from sqlalchemy import REAL, CheckConstraint, DateTime, ForeignKey, Index, Text, func, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base
from app.db.models.enums import Sentiment, pg_enum

_SHA256_HEX = "'^[0-9a-f]{64}$'"


class ContentAnalysisRow(Base):
    """Output of the local NLP pipeline for one content item (Phase 4.2).

    docs/DATABASE.md section 5.6. One row per `content_items` row. `(content_hash,
    analyzer_version)` is the reuse key: an item whose text was already analyzed under the same
    version gets the stored model results copied instead of new inference. Deleting the content
    item (e.g. through its analysis) deletes this row.
    """

    __tablename__ = "content_analysis"
    __table_args__ = (
        CheckConstraint("sentiment_score BETWEEN -1 AND 1", name="sentiment_score_range"),
        CheckConstraint("negative_prob BETWEEN 0 AND 1", name="negative_prob_range"),
        CheckConstraint(f"content_hash ~ {_SHA256_HEX}", name="content_hash_sha256_hex"),
        CheckConstraint("model ~ '\\S'", name="model_not_blank"),
        CheckConstraint("analyzer_version ~ '\\S'", name="analyzer_version_not_blank"),
        Index(
            "ix_content_analysis_content_hash_analyzer_version", "content_hash", "analyzer_version"
        ),
    )

    content_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("content_items.id", ondelete="CASCADE"),
        primary_key=True,
    )
    content_hash: Mapped[str] = mapped_column(Text, nullable=False)
    sentiment: Mapped[Sentiment] = mapped_column(pg_enum(Sentiment, "sentiment"), nullable=False)
    sentiment_score: Mapped[float] = mapped_column(REAL, nullable=False)
    negative_prob: Mapped[float] = mapped_column(REAL, nullable=False)
    is_about_brand: Mapped[bool] = mapped_column(nullable=False)
    matched_terms: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'::text[]")
    )
    topics: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'::text[]")
    )
    keywords: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'::text[]")
    )
    model: Mapped[str] = mapped_column(Text, nullable=False)
    analyzer_version: Mapped[str] = mapped_column(Text, nullable=False)
    analyzed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
