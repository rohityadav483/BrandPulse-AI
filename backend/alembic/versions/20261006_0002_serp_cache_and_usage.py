"""serp_cache and serp_usage

Phase 2 migration (docs/DATABASE.md section 9, tables 5.4 and 5.15).

- `serp_cache`: raw SerpApi responses keyed by request hash, with `pinned` demo entries.
- `serp_usage`: one row per request attempt, with `account_label` for the monthly counter.
  `investigation_id` is a plain column; the Phase 7 migration adds its foreign key.
  `analysis_id` uses ON DELETE SET NULL so deleting an analysis never refunds spent credits.
  Two check constraints guard what the code relies on: `credits` is 0 or 1 and `purpose` is one
  of the four documented values.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "serp_cache",
        sa.Column("cache_key", sa.Text(), nullable=False),
        sa.Column("engine", sa.Text(), nullable=False),
        sa.Column("params", postgresql.JSONB(), nullable=False),
        sa.Column("response", postgresql.JSONB(), nullable=False),
        sa.Column("http_status", sa.SmallInteger(), nullable=True),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("pinned", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.PrimaryKeyConstraint("cache_key", name=op.f("pk_serp_cache")),
    )
    op.create_index("ix_serp_cache_expires_at", "serp_cache", ["expires_at"])

    op.create_table(
        "serp_usage",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("cache_key", sa.Text(), nullable=False),
        sa.Column("engine", sa.Text(), nullable=False),
        sa.Column("cache_hit", sa.Boolean(), nullable=False),
        sa.Column("credits", sa.SmallInteger(), nullable=False),
        sa.Column("http_status", sa.SmallInteger(), nullable=True),
        sa.Column("analysis_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("investigation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("purpose", sa.Text(), nullable=False),
        sa.Column("account_label", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("credits BETWEEN 0 AND 1", name=op.f("ck_serp_usage_credits_range")),
        sa.CheckConstraint(
            "purpose IN ('analysis', 'investigation', 'fixture_recording', 'probe')",
            name=op.f("ck_serp_usage_purpose_allowed"),
        ),
        sa.ForeignKeyConstraint(
            ["analysis_id"],
            ["analyses.id"],
            name=op.f("fk_serp_usage_analysis_id_analyses"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_serp_usage")),
    )
    op.create_index("ix_serp_usage_created_at", "serp_usage", ["created_at"])


def downgrade() -> None:
    # Dropping a table drops its indexes.
    op.drop_table("serp_usage")
    op.drop_table("serp_cache")
