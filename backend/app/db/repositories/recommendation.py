from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.recommendation import Recommendation


class RecommendationRepository:
    def __init__(self, engine):
        self.engine = engine

    def add_many(self, rows):
        if not rows:
            return []
        with Session(self.engine) as s:
            objs = [Recommendation(**r) for r in rows]
            s.add_all(objs)
            s.commit()
            for o in objs:
                s.refresh(o)
            return objs

    def list_for_investigation(self, investigation_id: UUID):
        with Session(self.engine) as s:
            return s.scalars(
                select(Recommendation)
                .where(Recommendation.investigation_id == investigation_id)
                .order_by(Recommendation.created_at)
            ).all()
