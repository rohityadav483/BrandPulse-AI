from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models.investigation import Evidence, Investigation


class InvestigationRepository:
    def __init__(self, engine):
        self.engine = engine

    def create(self, signal_id: UUID, analysis_id: UUID) -> Investigation:
        with Session(self.engine) as s:
            row = Investigation(signal_id=signal_id, analysis_id=analysis_id)
            s.add(row)
            s.commit()
            s.refresh(row)
            return row

    def latest_for_signal(self, signal_id: UUID):
        with Session(self.engine) as s:
            return s.scalar(
                select(Investigation)
                .where(Investigation.signal_id == signal_id)
                .order_by(Investigation.created_at.desc())
                .limit(1)
            )

    def get(self, investigation_id: UUID):
        with Session(self.engine) as s:
            return s.get(Investigation, investigation_id)


class EvidenceRepository:
    def __init__(self, engine):
        self.engine = engine

    def add_many(self, rows: list[dict]):
        if not rows:
            return
        with Session(self.engine) as s:
            s.add_all([Evidence(**r) for r in rows])
            s.commit()

    def list(
        self,
        investigation_id: UUID,
        *,
        stance=None,
        source_type=None,
        page=1,
        page_size=20,
    ):
        with Session(self.engine) as s:
            q = select(Evidence).where(Evidence.investigation_id == investigation_id)
            if stance:
                q = q.where(
                    Evidence.stance == stance.value
                    if hasattr(stance, "value")
                    else stance
                )
            if source_type:
                from app.db.models.content_item import ContentItemRow

                q = q.join(
                    ContentItemRow, ContentItemRow.id == Evidence.content_id
                ).where(
                    ContentItemRow.source_type
                    == (
                        source_type.value
                        if hasattr(source_type, "value")
                        else source_type
                    )
                )
            total = s.scalar(select(func.count()).select_from(q.subquery())) or 0
            rows = s.scalars(
                q.order_by(Evidence.rank)
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).all()
            counts = {
                k: s.scalar(
                    select(func.count())
                    .select_from(Evidence)
                    .where(
                        Evidence.investigation_id == investigation_id,
                        Evidence.stance == k,
                    )
                )
                or 0
                for k in ("supports", "contradicts", "neutral")
            }
            return rows, total, counts
