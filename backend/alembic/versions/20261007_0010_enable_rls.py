"""enable row-level security on application tables

RLS is enabled without FORCE so the backend table owner keeps working. Supabase anon/authenticated
roles have no policies and therefore cannot read/write these tables directly; the browser uses FastAPI.
"""

from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

TABLES = (
    "brands",
    "analyses",
    "analysis_brands",
    "serp_cache",
    "serp_usage",
    "raw_items",
    "content_items",
    "content_analysis",
    "item_aspects",
    "trend_points",
    "brand_snapshots",
    "signals",
    "llm_calls",
    "investigations",
    "evidence",
    "recommendations",
)


def upgrade():
    for table in TABLES:
        op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')


def downgrade():
    for table in reversed(TABLES):
        op.execute(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY')
