import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    REAL,
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base
from app.db.models.enums import ImpactLevel, SignalKind, SignalStatus, pg_enum


class TrendPoint(Base):
    __tablename__ = "trend_points"
    __table_args__ = (
        Index(
            "uq_trend_points_identity",
            "analysis_id",
            "brand_id",
            "keyword",
            "date",
            unique=True,
        ),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    analysis_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("analyses.id", ondelete="CASCADE"), nullable=False
    )
    brand_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("brands.id"), nullable=False)
    keyword: Mapped[str] = mapped_column(Text, nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    value: Mapped[int] = mapped_column(SmallInteger, nullable=False)


class BrandSnapshot(Base):
    __tablename__ = "brand_snapshots"
    analysis_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("analyses.id", ondelete="CASCADE"), primary_key=True
    )
    brand_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("brands.id"), primary_key=True
    )
    sample_size: Mapped[int] = mapped_column(Integer, nullable=False)
    baseline_sample_size: Mapped[int] = mapped_column(Integer, nullable=False)
    sentiment_dist: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    aspect_scores: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    topic_counts: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    source_mix: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    health: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    interest_change_pct: Mapped[float | None] = mapped_column(REAL)
    low_data: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Signal(Base):
    __tablename__ = "signals"
    __table_args__ = (
        Index("ix_signals_analysis_brand", "analysis_id", "brand_id"),
        Index("ix_signals_analysis_score", "analysis_id", "signal_score"),
    )
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    analysis_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("analyses.id", ondelete="CASCADE"), nullable=False
    )
    brand_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("brands.id"), nullable=False)
    kind: Mapped[SignalKind] = mapped_column(
        pg_enum(SignalKind, "signal_kind"), nullable=False
    )
    aspect: Mapped[str] = mapped_column(Text, nullable=False)
    baseline_n: Mapped[int] = mapped_column(Integer, nullable=False)
    baseline_total: Mapped[int] = mapped_column(Integer, nullable=False)
    current_n: Mapped[int] = mapped_column(Integer, nullable=False)
    current_total: Mapped[int] = mapped_column(Integer, nullable=False)
    baseline_share: Mapped[float] = mapped_column(REAL, nullable=False)
    current_share: Mapped[float] = mapped_column(REAL, nullable=False)
    growth: Mapped[float] = mapped_column(REAL, nullable=False)
    components: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    signal_score: Mapped[float] = mapped_column(REAL, nullable=False)
    impact: Mapped[ImpactLevel] = mapped_column(
        pg_enum(ImpactLevel, "impact_level"), nullable=False
    )
    signal_confidence: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    sources_count: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    source_types: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    trend_corroborated: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    status: Mapped[SignalStatus] = mapped_column(
        pg_enum(SignalStatus, "signal_status"),
        nullable=False,
        server_default=text("'detected'"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
