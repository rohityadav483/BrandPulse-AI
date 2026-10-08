"""Phase 5 repositories: trend points, brand snapshots, signals.

Like every other repository these take an `Engine` and run each call in one short transaction
(writes commit before returning). Returned ORM rows are detached but fully loaded
(`expire_on_commit=False`), so callers can read their attributes after the call.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.db.models.phase5 import BrandSnapshot, Signal, TrendPoint


class TrendPointRepository:
    def __init__(self, engine: Engine):
        self._engine = engine

    def add_many(self, rows: list[dict[str, Any]]) -> int:
        if not rows:
            return 0
        with Session(self._engine, expire_on_commit=False) as session, session.begin():
            session.add_all([TrendPoint(**r) for r in rows])
        return len(rows)

    def list_for_brand(
        self, analysis_id: uuid.UUID, brand_id: uuid.UUID, keyword: str | None = None
    ) -> list[TrendPoint]:
        q = select(TrendPoint).where(
            TrendPoint.analysis_id == analysis_id, TrendPoint.brand_id == brand_id
        )
        if keyword is not None:
            q = q.where(TrendPoint.keyword == keyword)
        with Session(self._engine, expire_on_commit=False) as session:
            return list(session.scalars(q.order_by(TrendPoint.date)).all())


class BrandSnapshotRepository:
    def __init__(self, engine: Engine):
        self._engine = engine

    def upsert(self, row: dict[str, Any]) -> BrandSnapshot:
        with Session(self._engine, expire_on_commit=False) as session, session.begin():
            obj = session.get(BrandSnapshot, (row["analysis_id"], row["brand_id"]))
            if obj is None:
                obj = BrandSnapshot(**row)
                session.add(obj)
            else:
                for k, v in row.items():
                    setattr(obj, k, v)
            session.flush()
            session.refresh(obj)  # load server defaults (created_at) before the session closes
        return obj

    def get(self, analysis_id: uuid.UUID, brand_id: uuid.UUID) -> BrandSnapshot | None:
        with Session(self._engine, expire_on_commit=False) as session:
            return session.get(BrandSnapshot, (analysis_id, brand_id))


class SignalRepository:
    def __init__(self, engine: Engine):
        self._engine = engine

    def add_many(self, rows: list[dict[str, Any]]) -> list[Signal]:
        objects = [Signal(**r) for r in rows]
        if not objects:
            return objects
        with Session(self._engine, expire_on_commit=False) as session, session.begin():
            session.add_all(objects)
            session.flush()
            for obj in objects:
                session.refresh(obj)  # load id/status/created_at server defaults
        return objects

    def list_for_analysis(self, analysis_id: uuid.UUID) -> list[Signal]:
        q = (
            select(Signal)
            .where(Signal.analysis_id == analysis_id)
            .order_by(Signal.signal_score.desc(), Signal.created_at)
        )
        with Session(self._engine, expire_on_commit=False) as session:
            return list(session.scalars(q).all())

    def get(self, signal_id: uuid.UUID) -> Signal | None:
        with Session(self._engine, expire_on_commit=False) as session:
            return session.get(Signal, signal_id)
