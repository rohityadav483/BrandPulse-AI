import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
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
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base
from app.db.models.enums import (
    AnalysisStage,
    AnalysisStatus,
    BrandRole,
    pg_enum,
)


class Analysis(Base):
    """One row per analysis run. docs/DATABASE.md section 5.2."""

    __tablename__ = "analyses"
    __table_args__ = (
        CheckConstraint("char_length(product) <= 80", name="product_max_80"),
        CheckConstraint("period_days IN (7, 14, 30)", name="period_days_allowed"),
        CheckConstraint("progress BETWEEN 0 AND 100", name="progress_range"),
        Index("ix_analyses_created_at", text("created_at DESC")),
        Index("ix_analyses_client_ip_hash_created_at", "client_ip_hash", "created_at"),
        Index("ix_analyses_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    brand_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("brands.id"), nullable=False)
    product: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(
        Text, server_default=text("'consumer_electronics'")
    )
    period_days: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default=text("30")
    )
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)
    current_start: Mapped[date] = mapped_column(Date, nullable=False)
    current_end: Mapped[date] = mapped_column(Date, nullable=False)
    baseline_start: Mapped[date] = mapped_column(Date, nullable=False)
    baseline_end: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[AnalysisStatus] = mapped_column(
        pg_enum(AnalysisStatus, "analysis_status"),
        nullable=False,
        server_default=text("'queued'"),
    )
    stage: Mapped[AnalysisStage | None] = mapped_column(pg_enum(AnalysisStage, "analysis_stage"))
    progress: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default=text("0"))
    warnings: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    serp_calls_used: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    serp_calls_budget: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("12")
    )
    live_run: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    error: Mapped[str | None] = mapped_column(Text)
    client_ip_hash: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AnalysisBrand(Base):
    """Target and competitors for one analysis. docs/DATABASE.md section 5.3."""

    __tablename__ = "analysis_brands"
    __table_args__ = (
        # Exactly one target per analysis (also enforced in the app).
        Index(
            "uq_analysis_brands_one_target",
            "analysis_id",
            unique=True,
            postgresql_where=text("role = 'target'"),
        ),
    )

    analysis_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("analyses.id", ondelete="CASCADE"), primary_key=True
    )
    # brands rows are never cascade-deleted (DATABASE.md section 8).
    brand_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("brands.id"), primary_key=True)
    role: Mapped[BrandRole] = mapped_column(pg_enum(BrandRole, "brand_role"), nullable=False)
