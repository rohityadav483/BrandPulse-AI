import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ENUM
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base


class LLMCall(Base):
    """Audit record for an LLM provider call."""

    __tablename__ = "llm_calls"
    __table_args__ = (
        Index("ix_llm_calls_analysis_created_at", "analysis_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    analysis_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("analyses.id"),
    )

    investigation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("investigations.id", ondelete="SET NULL"),
    )

    task: Mapped[str] = mapped_column(Text, nullable=False)

    provider: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default=text("'groq'"),
    )

    model: Mapped[str] = mapped_column(Text, nullable=False)

    prompt_version: Mapped[str] = mapped_column(Text, nullable=False)

    attempt: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        server_default=text("1"),
    )

    tokens_in: Mapped[int | None] = mapped_column(Integer)

    tokens_out: Mapped[int | None] = mapped_column(Integer)

    latency_ms: Mapped[int | None] = mapped_column(Integer)

    status: Mapped[str] = mapped_column(
        ENUM(
            "ok",
            "retry",
            "rate_limited",
            "invalid_json",
            "failed",
            name="llm_call_status",
            create_type=False,
        ),
        nullable=False,
    )

    error: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
