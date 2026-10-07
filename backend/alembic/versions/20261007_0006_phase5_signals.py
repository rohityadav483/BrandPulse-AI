"""phase 5 trend points snapshots signals

Revision ID: 0006
Revises: 0005
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade():
    impact = postgresql.ENUM(
        "low", "medium", "high", name="impact_level", create_type=False
    )
    kind = postgresql.ENUM(
        "aspect_negative_spike", name="signal_kind", create_type=False
    )
    status = postgresql.ENUM(
        "detected",
        "investigating",
        "investigated",
        name="signal_status",
        create_type=False,
    )
    op.create_table(
        "trend_points",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("analysis_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("brand_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("keyword", sa.Text(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("value", sa.SmallInteger(), nullable=False),
        sa.ForeignKeyConstraint(["analysis_id"], ["analyses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["brand_id"], ["brands.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_trend_points_identity",
        "trend_points",
        ["analysis_id", "brand_id", "keyword", "date"],
        unique=True,
    )
    op.create_table(
        "brand_snapshots",
        sa.Column("analysis_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("brand_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sample_size", sa.Integer(), nullable=False),
        sa.Column("baseline_sample_size", sa.Integer(), nullable=False),
        sa.Column("sentiment_dist", postgresql.JSONB(), nullable=False),
        sa.Column("aspect_scores", postgresql.JSONB(), nullable=False),
        sa.Column("topic_counts", postgresql.JSONB(), nullable=False),
        sa.Column("source_mix", postgresql.JSONB(), nullable=False),
        sa.Column("health", postgresql.JSONB(), nullable=False),
        sa.Column("interest_change_pct", sa.REAL(), nullable=True),
        sa.Column("low_data", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["analysis_id"], ["analyses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["brand_id"], ["brands.id"]),
        sa.PrimaryKeyConstraint("analysis_id", "brand_id"),
    )
    op.create_table(
        "signals",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("analysis_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("brand_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", kind, nullable=False),
        sa.Column("aspect", sa.Text(), nullable=False),
        sa.Column("baseline_n", sa.Integer(), nullable=False),
        sa.Column("baseline_total", sa.Integer(), nullable=False),
        sa.Column("current_n", sa.Integer(), nullable=False),
        sa.Column("current_total", sa.Integer(), nullable=False),
        sa.Column("baseline_share", sa.REAL(), nullable=False),
        sa.Column("current_share", sa.REAL(), nullable=False),
        sa.Column("growth", sa.REAL(), nullable=False),
        sa.Column("components", postgresql.JSONB(), nullable=False),
        sa.Column("signal_score", sa.REAL(), nullable=False),
        sa.Column("impact", impact, nullable=False),
        sa.Column("signal_confidence", sa.SmallInteger(), nullable=False),
        sa.Column("sources_count", sa.SmallInteger(), nullable=False),
        sa.Column("source_types", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column(
            "trend_corroborated",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "status", status, server_default=sa.text("'detected'"), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["analysis_id"], ["analyses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["brand_id"], ["brands.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_signals_analysis_brand", "signals", ["analysis_id", "brand_id"])
    op.create_index(
        "ix_signals_analysis_score", "signals", ["analysis_id", "signal_score"]
    )


def downgrade():
    op.drop_index("ix_signals_analysis_score", table_name="signals")
    op.drop_index("ix_signals_analysis_brand", table_name="signals")
    op.drop_table("signals")
    op.drop_table("brand_snapshots")
    op.drop_index("uq_trend_points_identity", table_name="trend_points")
    op.drop_table("trend_points")
