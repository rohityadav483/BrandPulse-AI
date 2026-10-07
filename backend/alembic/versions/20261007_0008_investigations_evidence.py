"""add investigations and evidence for Phase 7"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "investigations",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("signal_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("analysis_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "status", sa.Text(), nullable=False, server_default=sa.text("'queued'")
        ),
        sa.Column(
            "step",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'generating_queries'"),
        ),
        sa.Column(
            "steps",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("report", postgresql.JSONB(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["signal_id"], ["signals.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["analysis_id"], ["analyses.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "status IN ('queued','running','completed','failed')",
            name="investigation_status_allowed",
        ),
    )
    op.create_index("ix_investigations_signal", "investigations", ["signal_id"])
    op.create_index(
        "ix_investigations_analysis_created",
        "investigations",
        ["analysis_id", "created_at"],
    )
    op.create_table(
        "evidence",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("investigation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("content_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("stance", sa.Text(), nullable=False),
        sa.Column("relevance", sa.REAL(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("rank", sa.SmallInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["investigation_id"], ["investigations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["content_id"], ["content_items.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "stance IN ('supports','contradicts','neutral')",
            name="evidence_stance_allowed",
        ),
        sa.CheckConstraint(
            "relevance >= 0 AND relevance <= 1", name="evidence_relevance_range"
        ),
        sa.CheckConstraint("rank >= 1", name="evidence_rank_positive"),
    )
    op.create_index(
        "ix_evidence_investigation_rank", "evidence", ["investigation_id", "rank"]
    )
    op.create_index(
        "ix_evidence_investigation_stance", "evidence", ["investigation_id", "stance"]
    )
    # Add FKs requested by Phase 7 to existing optional logging columns.
    op.create_foreign_key(
        "fk_llm_calls_investigation",
        "llm_calls",
        "investigations",
        ["investigation_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_serp_usage_investigation",
        "serp_usage",
        "investigations",
        ["investigation_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade():
    op.drop_constraint("fk_serp_usage_investigation", "serp_usage", type_="foreignkey")
    op.drop_constraint("fk_llm_calls_investigation", "llm_calls", type_="foreignkey")
    op.drop_index("ix_evidence_investigation_stance", table_name="evidence")
    op.drop_index("ix_evidence_investigation_rank", table_name="evidence")
    op.drop_table("evidence")
    op.drop_index("ix_investigations_analysis_created", table_name="investigations")
    op.drop_index("ix_investigations_signal", table_name="investigations")
    op.drop_table("investigations")
