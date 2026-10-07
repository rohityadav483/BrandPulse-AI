"""add recommendations for Phase 8"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "recommendations",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("investigation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("priority", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column(
            "evidence_ids",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
        sa.Column("timeframe", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["investigation_id"], ["investigations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "priority IN ('low','medium','high')",
            name="recommendation_priority_allowed",
        ),
        sa.CheckConstraint(
            "char_length(title) > 0", name="recommendation_title_nonempty"
        ),
        sa.CheckConstraint(
            "char_length(action) > 0", name="recommendation_action_nonempty"
        ),
    )
    op.create_index(
        "ix_recommendations_investigation", "recommendations", ["investigation_id"]
    )


def downgrade():
    op.drop_index("ix_recommendations_investigation", table_name="recommendations")
    op.drop_table("recommendations")
