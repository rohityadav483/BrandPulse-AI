"""content_analysis and item_aspects

Phase 4.2 migration (docs/DATABASE.md sections 5.6 and 5.7).

`content_analysis`: one row per content item, output of the local NLP pipeline, reusable by
`(content_hash, analyzer_version)`. `item_aspects`: one row per item-aspect pair with the
analyzed clause. Both reference `content_items` with ON DELETE CASCADE, so deleting an analysis
(which cascades to its content items) removes its NLP rows too. Uses the existing `sentiment`
enum from 0001.

- Real (float4) columns follow DATABASE.md; stored scores carry float4 precision.
- `keywords`, `topics` and `matched_terms` default to an empty array.
- Check constraints guard ranges (scores in [-1, 1], probabilities in [0, 1]), non-blank
  text and the sha256 `content_hash`.

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SHA256_HEX = "'^[0-9a-f]{64}$'"


def _sentiment() -> postgresql.ENUM:
    """Reference the enum created by 0001 (values are literal so this file never drifts)."""
    return postgresql.ENUM(
        "positive", "neutral", "negative", name="sentiment", create_type=False
    )


def upgrade() -> None:
    empty_array = sa.text("'{}'::text[]")
    op.create_table(
        "content_analysis",
        sa.Column("content_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("content_hash", sa.Text(), nullable=False),
        sa.Column("sentiment", _sentiment(), nullable=False),
        sa.Column("sentiment_score", sa.REAL(), nullable=False),
        sa.Column("negative_prob", sa.REAL(), nullable=False),
        sa.Column("is_about_brand", sa.Boolean(), nullable=False),
        sa.Column(
            "matched_terms",
            postgresql.ARRAY(sa.Text()),
            server_default=empty_array,
            nullable=False,
        ),
        sa.Column(
            "topics",
            postgresql.ARRAY(sa.Text()),
            server_default=empty_array,
            nullable=False,
        ),
        sa.Column(
            "keywords",
            postgresql.ARRAY(sa.Text()),
            server_default=empty_array,
            nullable=False,
        ),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("analyzer_version", sa.Text(), nullable=False),
        sa.Column(
            "analyzed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "sentiment_score BETWEEN -1 AND 1",
            name=op.f("ck_content_analysis_sentiment_score_range"),
        ),
        sa.CheckConstraint(
            "negative_prob BETWEEN 0 AND 1",
            name=op.f("ck_content_analysis_negative_prob_range"),
        ),
        sa.CheckConstraint(
            f"content_hash ~ {SHA256_HEX}",
            name=op.f("ck_content_analysis_content_hash_sha256_hex"),
        ),
        sa.CheckConstraint(
            "model ~ '\\S'", name=op.f("ck_content_analysis_model_not_blank")
        ),
        sa.CheckConstraint(
            "analyzer_version ~ '\\S'",
            name=op.f("ck_content_analysis_analyzer_version_not_blank"),
        ),
        sa.ForeignKeyConstraint(
            ["content_id"],
            ["content_items.id"],
            name=op.f("fk_content_analysis_content_id_content_items"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("content_id", name=op.f("pk_content_analysis")),
    )
    op.create_index(
        "ix_content_analysis_content_hash_analyzer_version",
        "content_analysis",
        ["content_hash", "analyzer_version"],
    )

    op.create_table(
        "item_aspects",
        sa.Column("content_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("aspect", sa.Text(), nullable=False),
        sa.Column("clause", sa.Text(), nullable=False),
        sa.Column("sentiment", _sentiment(), nullable=False),
        sa.Column("negative_prob", sa.REAL(), nullable=False),
        sa.Column("score", sa.REAL(), nullable=False),
        sa.CheckConstraint(
            "aspect ~ '\\S'", name=op.f("ck_item_aspects_aspect_not_blank")
        ),
        sa.CheckConstraint(
            "clause ~ '\\S'", name=op.f("ck_item_aspects_clause_not_blank")
        ),
        sa.CheckConstraint(
            "negative_prob BETWEEN 0 AND 1",
            name=op.f("ck_item_aspects_negative_prob_range"),
        ),
        sa.CheckConstraint(
            "score BETWEEN -1 AND 1", name=op.f("ck_item_aspects_score_range")
        ),
        sa.ForeignKeyConstraint(
            ["content_id"],
            ["content_items.id"],
            name=op.f("fk_item_aspects_content_id_content_items"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("content_id", "aspect", name=op.f("pk_item_aspects")),
    )
    op.create_index(
        "ix_item_aspects_aspect_sentiment", "item_aspects", ["aspect", "sentiment"]
    )


def downgrade() -> None:
    # Dropping the tables drops their indexes; the `sentiment` enum belongs to 0001 and stays.
    op.drop_table("item_aspects")
    op.drop_table("content_analysis")
