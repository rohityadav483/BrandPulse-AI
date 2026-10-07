import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
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


class SerpCache(Base):
    """Raw SerpApi responses keyed by request hash. docs/DATABASE.md section 5.4."""

    __tablename__ = "serp_cache"
    __table_args__ = (Index("ix_serp_cache_expires_at", "expires_at"),)

    cache_key: Mapped[str] = mapped_column(Text, primary_key=True)
    engine: Mapped[str] = mapped_column(Text, nullable=False)
    params: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    response: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    http_status: Mapped[int | None] = mapped_column(SmallInteger)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    pinned: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )


class SerpUsage(Base):
    """One row per SerpApi request attempt; the monthly counter derives from it.

    docs/DATABASE.md section 5.15. `investigation_id` is a plain column until the Phase 7
    migration adds its foreign key. `analysis_id` is SET NULL on delete (not CASCADE): the credit
    was spent at SerpApi whether or not the analysis still exists, so the counter must not drop.
    """

    __tablename__ = "serp_usage"
    __table_args__ = (
        CheckConstraint("credits BETWEEN 0 AND 1", name="credits_range"),
        CheckConstraint(
            "purpose IN ('analysis', 'investigation', 'fixture_recording', 'probe')",
            name="purpose_allowed",
        ),
        Index("ix_serp_usage_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    cache_key: Mapped[str] = mapped_column(Text, nullable=False)
    engine: Mapped[str] = mapped_column(Text, nullable=False)
    cache_hit: Mapped[bool] = mapped_column(Boolean, nullable=False)
    credits: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    http_status: Mapped[int | None] = mapped_column(SmallInteger)
    analysis_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("analyses.id", ondelete="SET NULL")
    )
    investigation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    purpose: Mapped[str] = mapped_column(Text, nullable=False)
    account_label: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
