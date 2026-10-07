from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.content_item import ContentItemRow
from app.services.investigation.evidence_scorer import score_evidence


def collect_existing(engine, analysis_id, brand_id, aspect, limit=20):
    with Session(engine) as s:
        rows = s.scalars(
            select(ContentItemRow)
            .where(
                ContentItemRow.analysis_id == analysis_id,
                ContentItemRow.brand_id == brand_id,
            )
            .order_by(ContentItemRow.collected_at.desc())
            .limit(100)
        ).all()
    scored = score_evidence(rows, aspect)
    return scored[:limit]
