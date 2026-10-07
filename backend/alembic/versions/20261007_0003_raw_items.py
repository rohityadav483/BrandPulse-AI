"""raw_items

Phase 3.1 migration (docs/DATABASE.md section 5.4a).

`raw_items` persists the canonical `RawItem` that every SerpApi parser returns, exactly as
parsed: no cleaning, canonical URL, date parsing or dedupe (Phase 3.2 fills `content_items`
from these rows). Uses the existing `source_type`, `window_kind` and `content_purpose` enums
from 0001.

- `analysis_id` cascades on delete; `brand_id` does not (brands are never cascade-deleted).
- `serp_cache_key` has no foreign key: cache rows expire, raw items must outlive them.
- `uq_raw_items_identity` makes re-persisting the same parsed response a no-op.
- Check constraints guard what the code relies on (content engines only, non-blank title/url,
  positive position, sha256-hex `raw_key`, collection <=> window set).

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _enum(name: str, *values: str) -> postgresql.ENUM:
    """Reference an enum created by 0001 (values are literal so this file never drifts)."""
    return postgresql.ENUM(*values, name=name, create_type=False)


def upgrade() -> None:
    op.create_table(
        "raw_items",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("analysis_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("brand_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "purpose", _enum("content_purpose", "collection", "investigation"), nullable=False
        ),
        sa.Column("window", _enum("window_kind", "baseline", "current"), nullable=True),
        sa.Column(
            "source_type",
            _enum("source_type", "web", "news", "youtube", "forum", "shopping"),
            nullable=False,
        ),
        sa.Column("engine", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("snippet", sa.Text(), nullable=True),
        sa.Column("author", sa.Text(), nullable=True),
        sa.Column("published_raw", sa.Text(), nullable=True),
        sa.Column("published_iso", sa.Text(), nullable=True),
        sa.Column("position", sa.SmallInteger(), nullable=True),
        sa.Column("query", sa.Text(), nullable=True),
        sa.Column("serp_cache_key", sa.Text(), nullable=True),
        sa.Column(
            "metadata",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("raw_key", sa.Text(), nullable=False),
        sa.Column(
            "collected_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "engine IN ('google', 'google_news', 'google_forums', 'youtube')",
            name=op.f("ck_raw_items_engine_allowed"),
        ),
        sa.CheckConstraint("title ~ '\\S'", name=op.f("ck_raw_items_title_not_blank")),
        sa.CheckConstraint("url ~ '\\S'", name=op.f("ck_raw_items_url_not_blank")),
        sa.CheckConstraint(
            "position IS NULL OR position >= 1", name=op.f("ck_raw_items_position_positive")
        ),
        sa.CheckConstraint(
            "raw_key ~ '^[0-9a-f]{64}$'", name=op.f("ck_raw_items_raw_key_sha256_hex")
        ),
        sa.CheckConstraint(
            "(purpose = 'collection' AND \"window\" IS NOT NULL) "
            "OR (purpose = 'investigation' AND \"window\" IS NULL)",
            name=op.f("ck_raw_items_purpose_window_consistent"),
        ),
        sa.ForeignKeyConstraint(
            ["analysis_id"],
            ["analyses.id"],
            name=op.f("fk_raw_items_analysis_id_analyses"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["brand_id"], ["brands.id"], name=op.f("fk_raw_items_brand_id_brands")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_raw_items")),
    )
    op.create_index(
        "uq_raw_items_identity",
        "raw_items",
        ["analysis_id", "brand_id", "purpose", "raw_key"],
        unique=True,
    )
    op.create_index(
        "ix_raw_items_analysis_brand_window", "raw_items", ["analysis_id", "brand_id", "window"]
    )
    op.create_index(
        "ix_raw_items_analysis_source_type", "raw_items", ["analysis_id", "source_type"]
    )
    op.create_index("ix_raw_items_serp_cache_key", "raw_items", ["serp_cache_key"])


def downgrade() -> None:
    # Dropping the table drops its indexes; the enums belong to 0001 and stay.
    op.drop_table("raw_items")
