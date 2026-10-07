"""`serp_usage` access. Implements `services.serpapi.usage.UsageStore`.

Same transaction rule as `serp_cache`: every write commits on its own, so a spent credit is
never lost to a later rollback. Only `pipeline/` constructs and wires this class.
"""

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.db.models.serp import SerpUsage
from app.schemas.serp import UsageRecord


class SerpUsageRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def monthly_credits(self, account_label: str, start: datetime, end: datetime) -> int:
        """sum(credits) for one account label in [start, end)."""
        statement = select(func.coalesce(func.sum(SerpUsage.credits), 0)).where(
            SerpUsage.account_label == account_label,
            SerpUsage.created_at >= start,
            SerpUsage.created_at < end,
        )
        with Session(self._engine) as session:
            return int(session.execute(statement).scalar_one())

    def add(self, record: UsageRecord) -> None:
        row = SerpUsage(
            cache_key=record.cache_key,
            engine=record.engine,
            cache_hit=record.cache_hit,
            credits=record.credits,
            http_status=record.http_status,
            analysis_id=record.analysis_id,
            investigation_id=record.investigation_id,
            purpose=str(record.purpose),
            account_label=record.account_label,
            created_at=record.created_at,
        )
        with Session(self._engine) as session, session.begin():
            session.add(row)
