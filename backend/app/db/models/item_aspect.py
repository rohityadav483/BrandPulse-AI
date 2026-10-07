import uuid

from sqlalchemy import REAL, CheckConstraint, ForeignKey, Index, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base
from app.db.models.enums import Sentiment, pg_enum


class ItemAspectRow(Base):
    """Sentiment of one aspect clause of one content item (Phase 4.2).

    docs/DATABASE.md section 5.7. PK `(content_id, aspect)`: at most one clause per aspect.
    `clause` is the analyzed text and doubles as the evidence snippet in the UI.
    """

    __tablename__ = "item_aspects"
    __table_args__ = (
        CheckConstraint("aspect ~ '\\S'", name="aspect_not_blank"),
        CheckConstraint("clause ~ '\\S'", name="clause_not_blank"),
        CheckConstraint("negative_prob BETWEEN 0 AND 1", name="negative_prob_range"),
        CheckConstraint("score BETWEEN -1 AND 1", name="score_range"),
        Index("ix_item_aspects_aspect_sentiment", "aspect", "sentiment"),
    )

    content_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("content_items.id", ondelete="CASCADE"),
        primary_key=True,
    )
    aspect: Mapped[str] = mapped_column(Text, primary_key=True)
    clause: Mapped[str] = mapped_column(Text, nullable=False)
    sentiment: Mapped[Sentiment] = mapped_column(
        pg_enum(Sentiment, "sentiment"), nullable=False
    )
    negative_prob: Mapped[float] = mapped_column(REAL, nullable=False)
    score: Mapped[float] = mapped_column(REAL, nullable=False)
