"""add llm call log for Phase 6"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade():
    status = postgresql.ENUM(
        "ok",
        "retry",
        "rate_limited",
        "invalid_json",
        "failed",
        name="llm_call_status",
        create_type=False,
    )
    op.create_table(
        "llm_calls",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("analysis_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("investigation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("task", sa.Text(), nullable=False),
        sa.Column(
            "provider", sa.Text(), nullable=False, server_default=sa.text("'groq'")
        ),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("prompt_version", sa.Text(), nullable=False),
        sa.Column(
            "attempt", sa.SmallInteger(), nullable=False, server_default=sa.text("1")
        ),
        sa.Column("tokens_in", sa.Integer(), nullable=True),
        sa.Column("tokens_out", sa.Integer(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("status", status, nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["analysis_id"], ["analyses.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_llm_calls_analysis_created_at", "llm_calls", ["analysis_id", "created_at"]
    )


def downgrade():
    op.drop_index("ix_llm_calls_analysis_created_at", table_name="llm_calls")
    op.drop_table("llm_calls")
