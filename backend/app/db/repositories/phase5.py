from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.phase5 import BrandSnapshot, Signal, TrendPoint


class TrendPointRepository:
    def __init__(self, session: Session):
        self.session = session

    def add_many(self, rows: list[dict[str, Any]]) -> int:
        if rows:
            self.session.add_all([TrendPoint(**r) for r in rows])
            self.session.flush()
        return len(rows)

    def list_for_brand(
        self, analysis_id: uuid.UUID, brand_id: uuid.UUID, keyword: str | None = None
    ) -> list[TrendPoint]:
        q = select(TrendPoint).where(
            TrendPoint.analysis_id == analysis_id, TrendPoint.brand_id == brand_id
        )
        if keyword is not None:
            q = q.where(TrendPoint.keyword == keyword)
        return list(self.session.scalars(q.order_by(TrendPoint.date)).all())


class BrandSnapshotRepository:
    def __init__(self, session: Session):
        self.session = session

    def upsert(self, row: dict[str, Any]) -> BrandSnapshot:
        obj = self.session.get(BrandSnapshot, (row["analysis_id"], row["brand_id"]))
        if obj is None:
            obj = BrandSnapshot(**row)
            self.session.add(obj)
        else:
            for k, v in row.items():
                setattr(obj, k, v)
        self.session.flush()
        return obj

    def get(self, analysis_id: uuid.UUID, brand_id: uuid.UUID) -> BrandSnapshot | None:
        return self.session.get(BrandSnapshot, (analysis_id, brand_id))


class SignalRepository:
    def __init__(self, session: Session):
        self.session = session

    def add_many(self, rows: list[dict[str, Any]]) -> list[Signal]:
        objects = [Signal(**r) for r in rows]
        self.session.add_all(objects)
        self.session.flush()
        return objects

    def list_for_analysis(self, analysis_id: uuid.UUID) -> list[Signal]:
        q = (
            select(Signal)
            .where(Signal.analysis_id == analysis_id)
            .order_by(Signal.signal_score.desc(), Signal.created_at)
        )
        return list(self.session.scalars(q).all())

    def get(self, signal_id: uuid.UUID) -> Signal | None:
        return self.session.get(Signal, signal_id)
