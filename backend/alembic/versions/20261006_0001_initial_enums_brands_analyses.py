"""initial: enums, brands, analyses, analysis_brands

Phase 0 migration (docs/DATABASE.md section 9). Creates all enums from section 3 and the
first three tables. `gen_random_uuid()` is built into PostgreSQL 13+ (Supabase included),
so no `pgcrypto` extension is needed.

Revision ID: 0001
Revises:
Create Date: 2026-10-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# docs/DATABASE.md section 3. Values are literal on purpose: migrations must not
# change when application code changes.
ENUMS: dict[str, tuple[str, ...]] = {
    "analysis_status": ("queued", "running", "completed", "partial", "failed"),
    "analysis_stage": (
        "planning",
        "collecting",
        "processing",
        "analyzing",
        "detecting",
        "snapshotting",
        "done",
    ),
    "brand_role": ("target", "competitor", "suggested"),
    "source_type": ("web", "news", "youtube", "forum", "shopping"),
    "window_kind": ("baseline", "current"),
    "content_purpose": ("collection", "investigation"),
    "date_confidence": ("exact", "approximate", "unknown"),
    "sentiment": ("positive", "neutral", "negative"),
    "signal_kind": ("aspect_negative_spike",),
    "impact_level": ("low", "medium", "high"),
    "signal_status": ("detected", "investigating", "investigated"),
    "investigation_status": ("queued", "running", "completed", "failed"),
    "investigation_step": (
        "generating_queries",
        "collecting_evidence",
        "scoring_evidence",
        "comparing_competitors",
        "synthesizing",
        "recommending",
        "done",
    ),
    "scope_verdict": ("brand_specific", "industry_wide", "inconclusive", "unknown"),
    "stance": ("supports", "contradicts", "neutral"),
    "priority": ("low", "medium", "high"),
    "llm_call_status": ("ok", "retry", "rate_limited", "invalid_json", "failed"),
}


def _enum(name: str) -> postgresql.ENUM:
    """Reference an enum that already exists (created below with plain SQL)."""
    return postgresql.ENUM(*ENUMS[name], name=name, create_type=False)


def upgrade() -> None:
    for name, values in ENUMS.items():
        labels = ", ".join(f"'{v}'" for v in values)
        op.execute(f"CREATE TYPE {name} AS ENUM ({labels})")

    op.create_table(
        "brands",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("normalized_name", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_brands")),
        sa.UniqueConstraint("normalized_name", name=op.f("uq_brands_normalized_name")),
    )

    op.create_table(
        "analyses",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("brand_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("product", sa.Text(), nullable=True),
        sa.Column(
            "category",
            sa.Text(),
            server_default=sa.text("'consumer_electronics'"),
            nullable=True,
        ),
        sa.Column(
            "period_days",
            sa.SmallInteger(),
            server_default=sa.text("30"),
            nullable=False,
        ),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("current_start", sa.Date(), nullable=False),
        sa.Column("current_end", sa.Date(), nullable=False),
        sa.Column("baseline_start", sa.Date(), nullable=False),
        sa.Column("baseline_end", sa.Date(), nullable=False),
        sa.Column(
            "status",
            _enum("analysis_status"),
            server_default=sa.text("'queued'"),
            nullable=False,
        ),
        sa.Column("stage", _enum("analysis_stage"), nullable=True),
        sa.Column(
            "progress", sa.SmallInteger(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column(
            "warnings",
            postgresql.JSONB(),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "serp_calls_used", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column(
            "serp_calls_budget",
            sa.Integer(),
            server_default=sa.text("12"),
            nullable=False,
        ),
        sa.Column(
            "live_run", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("client_ip_hash", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "char_length(product) <= 80", name=op.f("ck_analyses_product_max_80")
        ),
        sa.CheckConstraint(
            "period_days IN (7, 14, 30)", name=op.f("ck_analyses_period_days_allowed")
        ),
        sa.CheckConstraint(
            "progress BETWEEN 0 AND 100", name=op.f("ck_analyses_progress_range")
        ),
        sa.ForeignKeyConstraint(
            ["brand_id"], ["brands.id"], name=op.f("fk_analyses_brand_id_brands")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_analyses")),
    )
    op.create_index("ix_analyses_created_at", "analyses", [sa.text("created_at DESC")])
    op.create_index(
        "ix_analyses_client_ip_hash_created_at",
        "analyses",
        ["client_ip_hash", "created_at"],
    )
    op.create_index("ix_analyses_status", "analyses", ["status"])

    op.create_table(
        "analysis_brands",
        sa.Column("analysis_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("brand_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", _enum("brand_role"), nullable=False),
        sa.ForeignKeyConstraint(
            ["analysis_id"],
            ["analyses.id"],
            name=op.f("fk_analysis_brands_analysis_id_analyses"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["brand_id"], ["brands.id"], name=op.f("fk_analysis_brands_brand_id_brands")
        ),
        sa.PrimaryKeyConstraint(
            "analysis_id", "brand_id", name=op.f("pk_analysis_brands")
        ),
    )
    op.create_index(
        "uq_analysis_brands_one_target",
        "analysis_brands",
        ["analysis_id"],
        unique=True,
        postgresql_where=sa.text("role = 'target'"),
    )


def downgrade() -> None:
    op.drop_table("analysis_brands")
    op.drop_table("analyses")
    op.drop_table("brands")
    for name in reversed(ENUMS):
        op.execute(f"DROP TYPE {name}")
