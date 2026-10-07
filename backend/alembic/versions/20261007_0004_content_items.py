"""content_items

Phase 3.2 migration (docs/DATABASE.md section 5.5).

`content_items` is the normalized store: canonical URL, domain, `url_hash`, `content_hash`,
parsed `published_at` with `date_confidence`, `window`, and `dup_group`. Filled from `raw_items`
(0003) by the Phase 3.2 pipeline stage. Uses the existing `source_type`, `window_kind`,
`content_purpose` and `date_confidence` enums from 0001.

- `analysis_id` cascades on delete; `brand_id` does not (brands are never cascade-deleted).
- `uq_content_items_identity` is the exact-dedupe rule from DATABASE.md: unique
  `(analysis_id, brand_id, content_hash)`.
- Extra lookup indexes beyond DATABASE.md: `(analysis_id, brand_id, url_hash)` for URL-level
  duplicate checks and `(analysis_id, dup_group)` for independence counting.
- Check constraints guard what the code relies on (content engines only, non-blank text,
  sha256-hex hashes, a date exists exactly when `date_confidence` is not 'unknown',
  investigation items have no window).
- No foreign key to `raw_items` or `serp_cache`: `serp_cache_key` is a trace pointer only.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SHA256_HEX = "'^[0-9a-f]{64}$'"


def _enum(name: str, *values: str) -> postgresql.ENUM:
    """Reference an enum created by 0001 (values are literal so this file never drifts)."""
    return postgresql.ENUM(*values, name=name, create_type=False)


def upgrade() -> None:
    op.create_table(
        "content_items",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("analysis_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("brand_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "purpose",
            _enum("content_purpose", "collection", "investigation"),
            nullable=False,
        ),
        sa.Column("window", _enum("window_kind", "baseline", "current"), nullable=True),
        sa.Column(
            "source_type",
            _enum("source_type", "web", "news", "youtube", "forum", "shopping"),
            nullable=False,
        ),
        sa.Column("engine", sa.Text(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("url_hash", sa.Text(), nullable=False),
        sa.Column("domain", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("snippet", sa.Text(), nullable=True),
        sa.Column("author", sa.Text(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "date_confidence",
            _enum("date_confidence", "exact", "approximate", "unknown"),
            nullable=False,
        ),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column(
            "metadata",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("content_hash", sa.Text(), nullable=False),
        sa.Column("dup_group", sa.Text(), nullable=True),
        sa.Column("serp_cache_key", sa.Text(), nullable=True),
        sa.Column(
            "collected_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "engine IN ('google', 'google_news', 'google_forums', 'youtube')",
            name=op.f("ck_content_items_engine_allowed"),
        ),
        sa.CheckConstraint(
            "title ~ '\\S'", name=op.f("ck_content_items_title_not_blank")
        ),
        sa.CheckConstraint("url ~ '\\S'", name=op.f("ck_content_items_url_not_blank")),
        sa.CheckConstraint(
            "domain ~ '\\S'", name=op.f("ck_content_items_domain_not_blank")
        ),
        sa.CheckConstraint(
            f"url_hash ~ {SHA256_HEX}",
            name=op.f("ck_content_items_url_hash_sha256_hex"),
        ),
        sa.CheckConstraint(
            f"content_hash ~ {SHA256_HEX}",
            name=op.f("ck_content_items_content_hash_sha256_hex"),
        ),
        sa.CheckConstraint(
            f"dup_group IS NULL OR dup_group ~ {SHA256_HEX}",
            name=op.f("ck_content_items_dup_group_sha256_hex"),
        ),
        sa.CheckConstraint(
            "(date_confidence = 'unknown') = (published_at IS NULL)",
            name=op.f("ck_content_items_date_matches_confidence"),
        ),
        sa.CheckConstraint(
            "purpose <> 'investigation' OR \"window\" IS NULL",
            name=op.f("ck_content_items_investigation_no_window"),
        ),
        sa.ForeignKeyConstraint(
            ["analysis_id"],
            ["analyses.id"],
            name=op.f("fk_content_items_analysis_id_analyses"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["brand_id"], ["brands.id"], name=op.f("fk_content_items_brand_id_brands")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_content_items")),
    )
    op.create_index(
        "uq_content_items_identity",
        "content_items",
        ["analysis_id", "brand_id", "content_hash"],
        unique=True,
    )
    op.create_index(
        "ix_content_items_analysis_brand_window",
        "content_items",
        ["analysis_id", "brand_id", "window"],
    )
    op.create_index(
        "ix_content_items_analysis_source_type",
        "content_items",
        ["analysis_id", "source_type"],
    )
    op.create_index("ix_content_items_content_hash", "content_items", ["content_hash"])
    op.create_index(
        "ix_content_items_analysis_brand_url_hash",
        "content_items",
        ["analysis_id", "brand_id", "url_hash"],
    )
    op.create_index(
        "ix_content_items_analysis_dup_group",
        "content_items",
        ["analysis_id", "dup_group"],
    )


def downgrade() -> None:
    # Dropping the table drops its indexes; the enums belong to 0001 and stay.
    op.drop_table("content_items")
