from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.v1.deps import SettingsDep, error_responses
from app.db.models.analysis import Analysis
from app.db.repositories.serp_usage import SerpUsageRepository
from app.db.session import get_engine
from app.schemas.api import AnalysesToday, UsageGroq, UsageResponse, UsageSerpapi
from app.services.serpapi.usage import MonthlyQuota

router = APIRouter(tags=["usage"])


@router.get(
    "/usage",
    response_model=UsageResponse,
    operation_id="getUsage",
    responses=error_responses(501),
)
def get_usage(settings: SettingsDep) -> UsageResponse:
    if not (settings.database_url or settings.database_url_direct):
        from app.api.v1.errors import ApiError

        raise ApiError(
            501, "not_implemented", "Database-backed usage requires DATABASE_URL."
        )
    engine = get_engine(settings.database_url or settings.database_url_direct)
    quota = MonthlyQuota(
        SerpUsageRepository(engine),
        account_label=settings.serpapi_account_label,
        limit=settings.serp_monthly_limit,
        reserve=settings.serp_monthly_reserve,
        allow_live=settings.allow_live_serpapi,
    ).snapshot()
    now = datetime.now(UTC)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    with Session(engine) as s:
        today = int(
            s.scalar(
                select(func.count())
                .select_from(Analysis)
                .where(Analysis.created_at >= start)
            )
            or 0
        )
    return UsageResponse(
        month=quota.month,
        serpapi=UsageSerpapi(
            limit=quota.limit,
            used=quota.used,
            remaining=quota.remaining,
            reserve=quota.reserve,
            live_enabled=quota.live_enabled,
        ),
        groq=UsageGroq(
            configured=settings.groq_configured,
            calls_today=0,
            model=settings.groq_model or None,
        ),
        analyses_today=AnalysesToday(used=today, limit=settings.max_analyses_per_day),
    )
