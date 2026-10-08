"""Analysis lifecycle endpoints (Phase 6)."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Header, Path, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.v1.deps import SettingsDep, error_responses
from app.api.v1.errors import ApiError
from app.db.models.analysis import Analysis, AnalysisBrand
from app.db.models.brand import Brand
from app.db.models.content_analysis import ContentAnalysisRow
from app.db.models.content_item import ContentItemRow
from app.db.models.item_aspect import ItemAspectRow
from app.db.models.phase5 import BrandSnapshot, Signal, TrendPoint
from app.db.repositories.serp_cache import SerpCacheRepository
from app.db.repositories.serp_usage import SerpUsageRepository
from app.db.session import get_engine
from app.pipeline.jobs import reap_stale_jobs_safe, start_analysis_job
from app.schemas.api import *
from app.schemas.domain import (
    AnalysisStatus,
    BrandRole,
    ContentPurpose,
    Sentiment,
    SourceType,
    WindowKind,
)
from app.services.demo_bundle import is_demo_id, section
from app.services.nlp.readiness import nlp_status
from app.services.serpapi.cache import ResponseCache
from app.services.serpapi.query_planner import build_plan
from app.services.serpapi.usage import MonthlyQuota

router = APIRouter(prefix="/analyses", tags=["analyses"])
AnalysisId = Annotated[
    str, Path(description="Analysis UUID (or a demo alias when DEMO_MODE=true).")
]
AccessCode = Annotated[
    str | None,
    Header(
        alias="X-Access-Code",
        description="Required only when new SerpApi calls are needed.",
    ),
]
_RATE: dict[str, list[datetime]] = {}


def _engine(settings):
    if not (settings.database_url or settings.database_url_direct):
        raise ApiError(
            501,
            "not_implemented",
            "Database-backed analysis endpoints require DATABASE_URL.",
        )
    return get_engine(settings.database_url or settings.database_url_direct)


def _has_db(settings) -> bool:
    return bool(settings.database_url or settings.database_url_direct)


def _demo_estimate(body: CreateAnalysisRequest, settings) -> EstimateAnalysisResponse:
    """DEMO_MODE without a database: the plan is computed, every call is 'cached' (bundle)."""
    plan = _plan(body, settings)
    windows = plan.windows
    limit = settings.serp_monthly_limit
    return EstimateAnalysisResponse(
        planned_calls=len(plan.calls),
        cached_calls=len(plan.calls),
        estimated_new_calls=0,
        as_of_date=windows.as_of_date,
        period=Period(
            current_start=windows.current_start,
            current_end=windows.current_end,
            baseline_start=windows.baseline_start,
            baseline_end=windows.baseline_end,
        ),
        serpapi=SerpapiQuota(
            limit=limit, used=0, remaining=limit, reserve=settings.serp_monthly_reserve
        ),
        live_enabled=False,
        needs_access_code=False,
        can_run=True,
        blocked_reason=None,
    )


def _demo_mentions(
    brand_id: UUID | None,
    aspect: str | None,
    sentiment: Sentiment | None,
    source_type: SourceType | None,
    page: int,
    page_size: int,
) -> ListMentionsResponse:
    """Mentions for the demo analysis, built from the bundle's evidence items."""
    bundle_signal = section("signal_detail")
    demo_aspect = str(bundle_signal.get("aspect", ""))
    target_id = section("dashboard")["target"]["brand"]["id"]
    items: list[MentionItem] = []
    if brand_id is None or str(brand_id) == str(target_id):
        for raw in section("evidence")["items"]:
            src = Source.model_validate(raw["source"])
            # Evidence that supports a negative spike is a negative mention.
            mention_sentiment = (
                Sentiment.negative if raw["stance"] == "supports" else Sentiment.neutral
            )
            if sentiment and mention_sentiment != sentiment:
                continue
            if source_type and src.source_type != source_type:
                continue
            if aspect and aspect != demo_aspect:
                continue
            items.append(
                MentionItem(
                    id=raw["id"],
                    source=src,
                    sentiment=mention_sentiment,
                    aspects=[
                        MentionAspect(
                            aspect=demo_aspect,
                            sentiment=mention_sentiment,
                            clause=raw.get("note") or src.title,
                        )
                    ],
                )
            )
    start = (page - 1) * page_size
    return ListMentionsResponse(
        items=items[start : start + page_size],
        page=page,
        page_size=page_size,
        total=len(items),
    )


def _period(a: Analysis) -> Period:
    return Period(
        current_start=a.current_start,
        current_end=a.current_end,
        baseline_start=a.baseline_start,
        baseline_end=a.baseline_end,
    )


def _ip_hash(request: Request) -> str:
    return hashlib.sha256(
        (request.client.host if request.client else "unknown").encode()
    ).hexdigest()


def _rate_ok(key: str) -> bool:
    now = datetime.now(UTC)
    cutoff = now - timedelta(minutes=1)
    values = [v for v in _RATE.get(key, []) if v > cutoff]
    if len(values) >= 10:
        _RATE[key] = values
        return False
    values.append(now)
    _RATE[key] = values
    return True


def _quota(settings):
    engine = _engine(settings)
    store = SerpUsageRepository(engine)
    return MonthlyQuota(
        store,
        account_label=settings.serpapi_account_label,
        limit=settings.serp_monthly_limit,
        reserve=settings.serp_monthly_reserve,
        allow_live=settings.allow_live_serpapi,
    )


def _plan(body: CreateAnalysisRequest, settings):
    as_of = body.as_of_date or datetime.now(UTC).date()
    return build_plan(
        brand=body.brand,
        product=body.product,
        competitors=body.competitors,
        as_of_date=as_of,
        period_days=body.period_days,
        max_calls=settings.serp_budget_per_analysis,
    )


@router.post(
    "/estimate",
    response_model=EstimateAnalysisResponse,
    operation_id="estimateAnalysis",
    summary="Cost preview; no side effects",
    responses=error_responses(400, 422, 501),
)
def estimate_analysis(
    body: CreateAnalysisRequest, settings: SettingsDep
) -> EstimateAnalysisResponse:
    if settings.demo_mode and not _has_db(settings):
        return _demo_estimate(body, settings)
    plan = _plan(body, settings)
    cache = ResponseCache(
        SerpCacheRepository(_engine(settings)), ttl_hours=settings.serp_cache_ttl_hours
    )
    cached = sum(cache.contains(call.spec) for call in plan.calls)
    new = len(plan.calls) - cached
    quota = _quota(settings).snapshot()
    daily = _daily_count(settings)
    blocked = None
    if daily >= settings.max_analyses_per_day:
        blocked = "daily_limit_reached"
    elif new and not settings.allow_live_serpapi:
        blocked = "live_data_disabled"
    elif new and quota.remaining - new < quota.reserve:
        blocked = "serpapi_quota_low"
    windows = plan.windows
    return EstimateAnalysisResponse(
        planned_calls=len(plan.calls),
        cached_calls=cached,
        estimated_new_calls=new,
        as_of_date=windows.as_of_date,
        period=Period(
            current_start=windows.current_start,
            current_end=windows.current_end,
            baseline_start=windows.baseline_start,
            baseline_end=windows.baseline_end,
        ),
        serpapi=SerpapiQuota(
            limit=quota.limit,
            used=quota.used,
            remaining=quota.remaining,
            reserve=quota.reserve,
        ),
        live_enabled=quota.live_enabled,
        needs_access_code=bool(new and settings.live_access_code.get_secret_value()),
        can_run=blocked is None,
        blocked_reason=blocked,
    )


def _daily_count(settings) -> int:
    with Session(_engine(settings)) as session:
        start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        return int(
            session.scalar(
                select(func.count())
                .select_from(Analysis)
                .where(Analysis.created_at >= start)
            )
            or 0
        )


@router.post(
    "",
    response_model=CreateAnalysisResponse,
    status_code=202,
    operation_id="createAnalysis",
    summary="Start an analysis",
    responses=error_responses(400, 403, 409, 422, 429, 501, 503),
)
def create_analysis(
    body: CreateAnalysisRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    settings: SettingsDep,
    x_access_code: AccessCode = None,
) -> CreateAnalysisResponse:
    if not _rate_ok(_ip_hash(request)):
        raise ApiError(429, "rate_limited", "Too many analysis requests.")
    if _daily_count(settings) >= settings.max_analyses_per_day:
        raise ApiError(429, "daily_limit_reached", "Daily analysis limit reached.")
    estimate = estimate_analysis(body, settings)
    if nlp_status(settings.sentiment_model, settings.hf_home) == "unavailable":
        raise ApiError(
            503,
            "nlp_unavailable",
            "Local sentiment model dependencies are unavailable.",
        )
    if not estimate.can_run:
        raise ApiError(
            409 if estimate.blocked_reason == "live_data_disabled" else 429,
            str(estimate.blocked_reason),
            "Analysis cannot run with the current data/quota settings.",
        )
    if (
        estimate.needs_access_code
        and settings.live_access_code.get_secret_value()
        and x_access_code != settings.live_access_code.get_secret_value()
    ):
        raise ApiError(
            403,
            "live_access_required",
            "A valid X-Access-Code is required for new live searches.",
        )
    engine = _engine(settings)
    reap_stale_jobs_safe(settings)
    windows = _plan(body, settings).windows
    with Session(engine) as session, session.begin():

        def get_or_create(name: str) -> Brand:
            normalized = " ".join(name.split()).casefold()
            brand = session.scalar(
                select(Brand).where(Brand.normalized_name == normalized)
            )
            if brand is None:
                brand = Brand(name=" ".join(name.split()), normalized_name=normalized)
                session.add(brand)
                session.flush()
            return brand

        target = get_or_create(body.brand)
        competitors = [get_or_create(x) for x in body.competitors]
        analysis = Analysis(
            brand_id=target.id,
            product=body.product,
            category=body.category.value,
            period_days=body.period_days,
            as_of_date=windows.as_of_date,
            current_start=windows.current_start,
            current_end=windows.current_end,
            baseline_start=windows.baseline_start,
            baseline_end=windows.baseline_end,
            serp_calls_budget=settings.serp_budget_per_analysis,
            client_ip_hash=_ip_hash(request),
        )
        session.add(analysis)
        session.flush()
        session.add(
            AnalysisBrand(
                analysis_id=analysis.id, brand_id=target.id, role=BrandRole.target
            )
        )
        for competitor in competitors:
            session.add(
                AnalysisBrand(
                    analysis_id=analysis.id,
                    brand_id=competitor.id,
                    role=BrandRole.competitor,
                )
            )
        analysis_id = analysis.id
    background_tasks.add_task(start_analysis_job, analysis_id, settings)
    return CreateAnalysisResponse(
        id=analysis_id,
        status=AnalysisStatus.queued,
        poll_url=f"/api/v1/analyses/{analysis_id}",
    )


@router.get(
    "",
    response_model=ListAnalysesResponse,
    operation_id="listAnalyses",
    responses=error_responses(422, 501),
)
def list_analyses(
    settings: SettingsDep, limit: Annotated[int, Query(ge=1, le=50)] = 10
) -> ListAnalysesResponse:
    with Session(_engine(settings)) as session:
        rows = session.execute(
            select(Analysis, Brand)
            .join(Brand, Brand.id == Analysis.brand_id)
            .order_by(Analysis.created_at.desc())
            .limit(limit)
        ).all()
        ids = [a.id for a, b in rows]
        signals = (
            session.scalars(
                select(Signal)
                .where(Signal.analysis_id.in_(ids))
                .order_by(Signal.signal_score.desc())
            ).all()
            if ids
            else []
        )
        top = {}
        for s in signals:
            top.setdefault(s.analysis_id, s)
        return ListAnalysesResponse(
            items=[
                AnalysisListItem(
                    id=a.id,
                    brand=b.name,
                    product=a.product,
                    status=a.status,
                    created_at=a.created_at,
                    top_signal=TopSignal(
                        aspect=top[a.id].aspect, impact=top[a.id].impact
                    )
                    if a.id in top
                    else None,
                )
                for a, b in rows
            ]
        )


@router.get(
    "/{id}",
    response_model=AnalysisStatusResponse,
    operation_id="getAnalysis",
    responses=error_responses(404, 422, 501),
)
def get_analysis(id: AnalysisId, settings: SettingsDep) -> AnalysisStatusResponse:
    if settings.demo_mode and is_demo_id(id):
        payload = section("dashboard")["analysis"]
        return AnalysisStatusResponse.model_validate(
            {
                **payload,
                "id": payload["id"],
                "brands": [
                    section("dashboard")["target"]["brand"],
                    *[x["brand"] for x in section("dashboard")["competitors"]],
                ],
                "stage": "done",
                "progress": 100,
                "serp_calls_used": 0,
                "serp_calls_budget": settings.serp_budget_per_analysis,
                "error": None,
                "created_at": "2026-08-10T10:00:00Z",
                "finished_at": "2026-08-10T10:00:00Z",
            }
        )
    if not (settings.database_url or settings.database_url_direct):
        raise ApiError(
            501,
            "not_implemented",
            "Database-backed analysis endpoints require DATABASE_URL.",
        )
    try:
        aid = UUID(id)
    except ValueError:
        raise ApiError(404, "not_found", "Unknown analysis ID.")
    with Session(_engine(settings)) as session:
        a = session.get(Analysis, aid)
        if a is None:
            raise ApiError(404, "not_found", "Unknown analysis ID.")
        brands = [
            BrandRef(id=b.id, name=b.name, role=ab.role)
            for b, ab in session.execute(
                select(Brand, AnalysisBrand)
                .join(AnalysisBrand, AnalysisBrand.brand_id == Brand.id)
                .where(AnalysisBrand.analysis_id == aid)
            ).all()
        ]
        warnings = [Warning(**w) for w in (a.warnings or [])]
        return AnalysisStatusResponse(
            id=a.id,
            status=a.status,
            stage=a.stage,
            progress=a.progress,
            brands=brands,
            product=a.product,
            period=_period(a),
            warnings=warnings,
            serp_calls_used=a.serp_calls_used,
            serp_calls_budget=a.serp_calls_budget,
            error=a.error,
            created_at=a.created_at,
            finished_at=a.finished_at,
        )


@router.get(
    "/{id}/dashboard",
    response_model=DashboardResponse,
    operation_id="getDashboard",
    responses=error_responses(404, 409, 422, 501),
)
def get_dashboard(id: AnalysisId, settings: SettingsDep) -> DashboardResponse:
    if settings.demo_mode and is_demo_id(id):
        return DashboardResponse.model_validate(section("dashboard"))
    try:
        aid = UUID(id)
    except ValueError:
        raise ApiError(404, "not_found", "Unknown analysis ID.")
    with Session(_engine(settings)) as session:
        a = session.get(Analysis, aid)
        if a is None:
            raise ApiError(404, "not_found", "Unknown analysis ID.")
        if a.status not in {AnalysisStatus.completed, AnalysisStatus.partial}:
            raise ApiError(409, "analysis_not_ready", "Analysis is not ready yet.")
        brand_rows = session.execute(
            select(Brand, AnalysisBrand)
            .join(AnalysisBrand, AnalysisBrand.brand_id == Brand.id)
            .where(AnalysisBrand.analysis_id == aid)
        ).all()
        snapshots = {
            s.brand_id: s
            for s in session.scalars(
                select(BrandSnapshot).where(BrandSnapshot.analysis_id == aid)
            ).all()
        }
        signals = session.scalars(
            select(Signal)
            .where(Signal.analysis_id == aid)
            .order_by(Signal.signal_score.desc())
        ).all()

        def search_interest(b, change_pct):
            """Stored Trends series for this brand's own keyword; None without data."""
            key = " ".join(b.name.split()).casefold()
            points = [
                SearchInterestPoint(date=tp.date, value=tp.value)
                for tp in session.scalars(
                    select(TrendPoint)
                    .where(TrendPoint.analysis_id == aid, TrendPoint.brand_id == b.id)
                    .order_by(TrendPoint.date)
                ).all()
                if " ".join(tp.keyword.split()).casefold() == key
            ]
            if not points:
                return None
            return SearchInterest(change_pct=change_pct, series=points)

        def brand_ref(b, role):
            return BrandRef(id=b.id, name=b.name, role=role)

        def snap_block(b, role):
            s = snapshots.get(b.id)
            data = s or BrandSnapshot(
                sample_size=0,
                baseline_sample_size=0,
                sentiment_dist={"positive": 0, "neutral": 0, "negative": 0},
                aspect_scores=[],
                topic_counts=[],
                source_mix={},
                health={
                    "overall": 0,
                    "sentiment": 0,
                    "engagement": 0,
                    "risk": 0,
                    "trend": 0,
                    "formula_version": "v1",
                },
                low_data=True,
                interest_change_pct=None,
            )
            growth = _growth_sample(session, aid, b.id)
            health = HealthScores(**data.health)
            dist = SentimentDistribution(**data.sentiment_dist)
            if role == BrandRole.target:
                return TargetBlock(
                    brand=brand_ref(b, role),
                    sample_size=data.sample_size,
                    baseline_sample_size=data.baseline_sample_size,
                    growth_sample_size=GrowthSampleSize(**growth),
                    low_data=data.low_data,
                    health=health,
                    sentiment=dist,
                    aspects=[AspectStat(**x) for x in data.aspect_scores],
                    topics=[TopicCount(**x) for x in data.topic_counts],
                    source_mix={SourceType(k): v for k, v in data.source_mix.items()},
                    search_interest=search_interest(b, data.interest_change_pct),
                )
            return CompetitorBlock(
                brand=brand_ref(b, role),
                sample_size=data.sample_size,
                low_data=data.low_data,
                sentiment=dist,
                aspects=[AspectStat(**x) for x in data.aspect_scores],
                search_interest=search_interest(b, data.interest_change_pct),
            )

        target = next((b, ab) for b, ab in brand_rows if ab.role == BrandRole.target)
        competitors = [
            (b, ab) for b, ab in brand_rows if ab.role == BrandRole.competitor
        ]
        warning = [Warning(**w) for w in (a.warnings or [])]
        sigs = [_signal_summary(s) for s in signals]
        return DashboardResponse(
            analysis=DashboardAnalysis(
                id=a.id,
                status=a.status,
                product=a.product,
                as_of_date=a.as_of_date,
                live_run=a.live_run,
                period=_period(a),
                warnings=warning,
            ),
            target=snap_block(target[0], target[1].role),
            competitors=[snap_block(b, ab.role) for b, ab in competitors],
            signals=sigs,
        )


def _growth_sample(session, aid, bid):
    q = (
        select(func.count())
        .select_from(ContentItemRow)
        .where(
            ContentItemRow.analysis_id == aid,
            ContentItemRow.brand_id == bid,
            ContentItemRow.purpose == ContentPurpose.collection,
            ContentItemRow.source_type.in_([SourceType.web, SourceType.news]),
            ContentItemRow.date_confidence.in_(["exact", "approximate"]),
        )
    )
    cur = int(session.scalar(q.where(ContentItemRow.window == WindowKind.current)) or 0)
    base = int(
        session.scalar(q.where(ContentItemRow.window == WindowKind.baseline)) or 0
    )
    return {"current": cur, "baseline": base}


def _signal_summary(s):
    return SignalSummary(
        id=s.id,
        brand_id=s.brand_id,
        kind=s.kind,
        aspect=s.aspect,
        growth=s.growth,
        impact=s.impact,
        confidence=s.signal_confidence,
        confidence_source="signal",
        sources_count=s.sources_count,
        source_types=[SourceType(x) for x in s.source_types],
        current_share=s.current_share,
        baseline_share=s.baseline_share,
        current_n=s.current_n,
        baseline_n=s.baseline_n,
        trend_corroborated=s.trend_corroborated,
        status=s.status,
    )


@router.get(
    "/{id}/mentions",
    response_model=ListMentionsResponse,
    operation_id="listMentions",
    responses=error_responses(404, 422, 501),
)
def list_mentions(
    id: AnalysisId,
    settings: SettingsDep,
    brand_id: UUID | None = None,
    aspect: str | None = None,
    sentiment: Sentiment | None = None,
    source_type: SourceType | None = None,
    window: WindowKind = WindowKind.current,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> ListMentionsResponse:
    if settings.demo_mode and is_demo_id(id):
        return _demo_mentions(brand_id, aspect, sentiment, source_type, page, page_size)
    try:
        aid = UUID(id)
    except ValueError:
        raise ApiError(404, "not_found", "Unknown analysis ID.")
    with Session(_engine(settings)) as session:
        target = brand_id or session.scalar(
            select(Analysis.brand_id).where(Analysis.id == aid)
        )
        if target is None:
            raise ApiError(404, "not_found", "Unknown analysis ID.")
        q = (
            select(ContentItemRow, ContentAnalysisRow)
            .join(
                ContentAnalysisRow, ContentAnalysisRow.content_id == ContentItemRow.id
            )
            .where(
                ContentItemRow.analysis_id == aid,
                ContentItemRow.brand_id == target,
                ContentItemRow.purpose == ContentPurpose.collection,
                ContentItemRow.window == window,
                ContentAnalysisRow.is_about_brand.is_(True),
            )
        )
        if sentiment:
            q = q.where(ContentAnalysisRow.sentiment == sentiment)
        if source_type:
            q = q.where(ContentItemRow.source_type == source_type)
        rows = session.execute(q.order_by(ContentItemRow.id)).all()
        out = []
        for item, analysis in rows:
            aspects = session.scalars(
                select(ItemAspectRow).where(ItemAspectRow.content_id == item.id)
            ).all()
            aspects = [x for x in aspects if aspect is None or x.aspect == aspect]
            if aspect and not aspects:
                continue
            out.append(
                MentionItem(
                    id=item.id,
                    source=Source(
                        source_type=item.source_type,
                        domain=item.domain,
                        url=item.url,
                        title=item.title,
                        snippet=item.snippet,
                        author=item.author,
                        published_at=item.published_at,
                        date_confidence=item.date_confidence,
                        collected_at=item.collected_at,
                    ),
                    sentiment=analysis.sentiment,
                    aspects=[
                        MentionAspect(
                            aspect=x.aspect, sentiment=x.sentiment, clause=x.clause
                        )
                        for x in aspects
                    ],
                )
            )
        total = len(out)
        start = (page - 1) * page_size
        return ListMentionsResponse(
            items=out[start : start + page_size],
            page=page,
            page_size=page_size,
            total=total,
        )
