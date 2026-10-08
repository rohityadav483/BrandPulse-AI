"""Phase 6 analysis pipeline: collect -> process -> analyze -> detect -> snapshot."""

from __future__ import annotations

import logging
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config.settings import Settings
from app.db.models.analysis import Analysis, AnalysisBrand
from app.db.models.brand import Brand
from app.db.models.content_item import ContentItemRow
from app.db.repositories.content_analysis import ContentAnalysisRepository
from app.db.repositories.content_item import ContentItemRepository
from app.db.repositories.phase5 import (
    BrandSnapshotRepository,
    SignalRepository,
    TrendPointRepository,
)
from app.db.repositories.raw_item import RawItemRepository
from app.db.repositories.serp_cache import SerpCacheRepository
from app.db.repositories.serp_usage import SerpUsageRepository
from app.db.session import get_engine
from app.schemas.domain import BrandRole, ContentPurpose, WindowKind
from app.schemas.serp import RawItemContext, UsagePurpose, WindowSet
from app.services.nlp.hf_sentiment import HFSentimentAnalyzer
from app.services.nlp.item_analysis import ItemText, analyze_items
from app.services.nlp.relevance import BrandProfile
from app.services.scoring.health import compute_health
from app.services.serpapi.budget import RunBudget
from app.services.serpapi.cache import ResponseCache
from app.services.serpapi.client import SerpApiClient
from app.services.serpapi.fetcher import SerpFetcher
from app.services.serpapi.parsers import parse_response
from app.services.serpapi.query_planner import build_plan
from app.services.serpapi.usage import MonthlyQuota
from app.services.signals.detector import detect_negative_spike
from app.services.signals.metrics import MetricItem
from app.services.signals.trends import interest_change_pct, trend_corroborated

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _RunContext:
    """Plain scalars copied out of the Analysis row inside the session.

    ORM instances expire on commit and detach when their session closes, so nothing read after
    the first session may touch an `Analysis` object.
    """

    analysis_id: UUID
    product: str | None
    category: str
    serp_calls_budget: int
    windows: WindowSet


@dataclass(frozen=True)
class _BrandCtx:
    """A brand and its role in this analysis, as plain values (no ORM instances)."""

    id: UUID
    name: str
    role: str


def _load_context(analysis: Analysis) -> _RunContext:
    """Call while `analysis` is attached and loaded (inside its session)."""
    return _RunContext(
        analysis_id=analysis.id,
        product=analysis.product,
        category=analysis.category or "consumer_electronics",
        serp_calls_budget=analysis.serp_calls_budget,
        windows=WindowSet(
            as_of_date=analysis.as_of_date,
            period_days=analysis.period_days,
            current_start=analysis.current_start,
            current_end=analysis.current_end,
            baseline_start=analysis.baseline_start,
            baseline_end=analysis.baseline_end,
        ),
    )


def _brands(session: Session, analysis_id: UUID) -> list[_BrandCtx]:
    rows = session.execute(
        select(Brand.id, Brand.name, AnalysisBrand.role)
        .join(AnalysisBrand, AnalysisBrand.brand_id == Brand.id)
        .where(AnalysisBrand.analysis_id == analysis_id)
        .order_by(AnalysisBrand.role, Brand.name)
    ).all()
    return [_BrandCtx(id=r.id, name=r.name, role=r.role) for r in rows]


def _make_fetcher(settings: Settings, engine):
    cache_repo = SerpCacheRepository(engine)
    usage_repo = SerpUsageRepository(engine)
    cache = ResponseCache(cache_repo, ttl_hours=settings.serp_cache_ttl_hours)
    quota = MonthlyQuota(
        usage_repo,
        account_label=settings.serpapi_account_label,
        limit=settings.serp_monthly_limit,
        reserve=settings.serp_monthly_reserve,
        allow_live=settings.allow_live_serpapi,
    )
    client = SerpApiClient(
        api_key=settings.serpapi_api_key.get_secret_value(),
        allow_live=settings.allow_live_serpapi,
    )
    return SerpFetcher(cache=cache, quota=quota, client=client), cache, quota


def _norm_name(name: str) -> str:
    return " ".join(name.split()).casefold()


def _persist_trends(engine, analysis_id: UUID, brands: list[_BrandCtx], parsed) -> None:
    """Store Trends points under the brand each keyword names (one call covers several)."""
    if parsed.trends is None:
        return
    by_keyword = {_norm_name(b.name): b.id for b in brands}
    rows = []
    for point in parsed.trends.points:
        # Trend date labels can be human-readable; timestamp is the stable source when present.
        if point.timestamp is not None:
            d = datetime.fromtimestamp(point.timestamp, tz=UTC).date()
        else:
            try:
                d = date.fromisoformat(point.date_raw[:10])
            except ValueError:
                continue
        for keyword, value in point.values.items():
            brand_id = by_keyword.get(_norm_name(keyword))
            if value is not None and brand_id is not None:
                rows.append(
                    {
                        "analysis_id": analysis_id,
                        "brand_id": brand_id,
                        "keyword": keyword,
                        "date": d,
                        "value": int(value),
                    }
                )
    if rows:
        TrendPointRepository(engine).add_many(rows)


def _interest_series(engine, analysis_id: UUID, brand: _BrandCtx) -> list[tuple[date, int]]:
    """Stored search-interest points for this brand's own keyword, oldest first."""
    key = _norm_name(brand.name)
    return [
        (r.date, r.value)
        for r in TrendPointRepository(engine).list_for_brand(analysis_id, brand.id)
        if _norm_name(r.keyword) == key
    ]


def _interest_change(
    engine, ctx: _RunContext, brand: _BrandCtx
) -> float | None:
    w = ctx.windows
    return interest_change_pct(
        _interest_series(engine, ctx.analysis_id, brand),
        baseline=(w.baseline_start, w.baseline_end),
        current=(w.current_start, w.current_end),
    )


def _analysis_items(engine, analysis_id: UUID, brand_id: UUID):
    with Session(engine) as session:
        return list(
            session.scalars(
                select(ContentItemRow)
                .where(
                    ContentItemRow.analysis_id == analysis_id,
                    ContentItemRow.brand_id == brand_id,
                    ContentItemRow.purpose == ContentPurpose.collection,
                )
                .order_by(ContentItemRow.id)
            ).all()
        )


def _brand_profile(brand: _BrandCtx, product: str | None) -> BrandProfile:
    """Terms that make an item "about" this brand.

    The analysed product belongs to the target brand only; a competitor is matched by its
    name. The brands table stores no aliases, so none are passed.
    """
    products = (product,) if product and brand.role == BrandRole.target else ()
    return BrandProfile(brand=brand.name, products=products, aliases=())


def _analyze_brand(
    engine,
    analysis_id: UUID,
    brand: _BrandCtx,
    category: str,
    analyzer,
    product: str | None = None,
) -> None:
    items = _analysis_items(engine, analysis_id, brand.id)
    if not items:
        return
    repo = ContentAnalysisRepository(engine)
    existing = repo.analyzed_content_ids(item.id for item in items)
    pending = [item for item in items if item.id not in existing]
    if not pending:
        return
    profile = _brand_profile(brand, product)
    texts = [ItemText(item.title, item.snippet) for item in pending]
    analyses = analyze_items(texts, profile, analyzer, category)
    from app.schemas.nlp import NewItemAnalysis

    writes = [
        NewItemAnalysis(
            content_id=item.id, content_hash=item.content_hash, analysis=result
        )
        for item, result in zip(pending, analyses, strict=True)
    ]
    repo.save_many(writes)


def _metric_rows(engine, analysis_id: UUID, brand_id: UUID) -> list[MetricItem]:
    with Session(engine) as session:
        rows = (
            session.execute(
                select(ContentItemRow).where(
                    ContentItemRow.analysis_id == analysis_id,
                    ContentItemRow.brand_id == brand_id,
                    ContentItemRow.purpose == ContentPurpose.collection,
                )
            )
            .scalars()
            .all()
        )
        # Item-level aspect rows are expanded into metric observations.
        from app.db.models.content_analysis import ContentAnalysisRow
        from app.db.models.item_aspect import ItemAspectRow

        aspects = (
            session.execute(
                select(ItemAspectRow)
                .join(ContentItemRow, ContentItemRow.id == ItemAspectRow.content_id)
                .where(
                    ContentItemRow.analysis_id == analysis_id,
                    ContentItemRow.brand_id == brand_id,
                    ContentItemRow.purpose == ContentPurpose.collection,
                )
            )
            .scalars()
            .all()
        )
        by_content = {r.id: r for r in rows}
        about_brand = {
            cid: flag
            for cid, flag in session.execute(
                select(ContentAnalysisRow.content_id, ContentAnalysisRow.is_about_brand).where(
                    ContentAnalysisRow.content_id.in_(list(by_content))
                )
            ).all()
        }
        return [
            MetricItem(
                window=by_content[a.content_id].window.value
                if by_content[a.content_id].window
                else "none",
                source_type=by_content[a.content_id].source_type.value,
                aspect=a.aspect,
                sentiment=a.sentiment.value,
                negative_prob=float(a.negative_prob),
                is_about_brand=about_brand.get(a.content_id, False),
                growth_eligible=by_content[a.content_id].source_type.value
                in {"web", "news"}
                and by_content[a.content_id].date_confidence.value
                in {"exact", "approximate"},
                item_id=str(a.content_id),
            )
            for a in aspects
        ]


def _snapshot(engine, ctx: _RunContext, brand: _BrandCtx) -> None:
    analysis_id = ctx.analysis_id
    from app.db.models.content_analysis import ContentAnalysisRow
    from app.db.models.item_aspect import ItemAspectRow

    with Session(engine) as session:
        rows = session.execute(
            select(ContentItemRow, ContentAnalysisRow)
            .join(
                ContentAnalysisRow, ContentAnalysisRow.content_id == ContentItemRow.id
            )
            .where(
                ContentItemRow.analysis_id == analysis_id,
                ContentItemRow.brand_id == brand.id,
                ContentItemRow.purpose == ContentPurpose.collection,
            )
        ).all()
        # Only items that are about the brand count as mentions of it.
        rows = [(r, a) for r, a in rows if a.is_about_brand]
        current = [r for r, _ in rows if r.window == WindowKind.current]
        baseline = [r for r, _ in rows if r.window == WindowKind.baseline]
        current_rows = [(r, a) for r, a in rows if r.window == WindowKind.current]
        sentiments = Counter(a.sentiment.value for _, a in current_rows)
        cur_analysis = {r.id: a for r, a in current_rows}
        aspects = (
            session.execute(
                select(ItemAspectRow).where(
                    ItemAspectRow.content_id.in_([r.id for r, _ in rows])
                )
            )
            .scalars()
            .all()
            if rows
            else []
        )
        by_aspect: dict[str, list] = defaultdict(list)
        for a in aspects:
            if a.content_id in cur_analysis:
                by_aspect[a.aspect].append(a)
        aspect_scores = []
        for aspect, vals in sorted(by_aspect.items()):
            pos = sum(v.sentiment.value == "positive" for v in vals)
            neg = sum(v.sentiment.value == "negative" for v in vals)
            total = len(vals)
            aspect_scores.append(
                {
                    "aspect": aspect,
                    "net_score": round((pos - neg) / total * 100) if total else 0,
                    "mentions": total,
                    "positive": round(pos / total * 100) if total else 0,
                    "neutral": round((total - pos - neg) / total * 100) if total else 0,
                    "negative": round(neg / total * 100) if total else 0,
                }
            )
        topics = Counter(
            t for r, a in rows if r.window == WindowKind.current for t in a.topics
        )
        source_mix = Counter(r.source_type.value for r in current)
        pos_pct = (
            sentiments["positive"] / len(current_rows) * 100 if current_rows else 0
        )
        neg_pct = (
            sentiments["negative"] / len(current_rows) * 100 if current_rows else 0
        )
        interest_change = _interest_change(engine, ctx, brand)
        health = compute_health(
            positive_pct=pos_pct,
            negative_pct=neg_pct,
            current_sample=len(current),
            baseline_sample=len(baseline),
            interest_change_pct=interest_change,
        )
        row = {
            "analysis_id": analysis_id,
            "brand_id": brand.id,
            "sample_size": len(current),
            "baseline_sample_size": len(baseline),
            "sentiment_dist": {
                "positive": round(pos_pct),
                "neutral": round(sentiments["neutral"] / len(current_rows) * 100)
                if current_rows
                else 0,
                "negative": round(neg_pct),
            },
            "aspect_scores": aspect_scores,
            "topic_counts": [{"topic": k, "count": v} for k, v in topics.most_common()],
            "source_mix": dict(source_mix),
            "health": {
                "overall": health.overall,
                "sentiment": health.sentiment,
                "engagement": health.engagement,
                "risk": health.risk,
                "trend": health.trend,
                "formula_version": health.formula_version,
            },
            "interest_change_pct": interest_change,
            "low_data": len(current) < 15,
        }
    BrandSnapshotRepository(engine).upsert(row)


def run_analysis(analysis_id: UUID, settings: Settings) -> None:
    engine = None
    try:
        engine = get_engine(settings.database_url or settings.database_url_direct)
        with Session(engine) as session:
            analysis = session.get(Analysis, analysis_id)
            if analysis is None:
                return
            analysis.status = "running"
            analysis.stage = "planning"
            analysis.progress = 5
            analysis.started_at = datetime.now(UTC)
            session.commit()
            # Copy scalars while the session is open; the instance is expired and detached after.
            ctx = _load_context(analysis)
            brand_rows = _brands(session, analysis_id)
    except Exception as exc:
        logger.exception(
            "analysis_pipeline_start_failed",
            extra={"analysis_id": str(analysis_id), "error_type": type(exc).__name__},
        )
        if engine is not None:
            try:
                with Session(engine) as session, session.begin():
                    analysis = session.get(Analysis, analysis_id)
                    if analysis is not None and analysis.status in {"queued", "running"}:
                        analysis.status = "failed"
                        analysis.error = "Analysis failed during startup. Check server logs for details."
                        analysis.finished_at = datetime.now(UTC)
            except Exception:
                logger.exception("analysis_pipeline_start_status_update_failed", extra={"analysis_id": str(analysis_id)})
        return
    try:
        fetcher, cache, _quota = _make_fetcher(settings, engine)
        windows = ctx.windows
        target_brand = next(b for b in brand_rows if b.role == BrandRole.target)
        plan = build_plan(
            brand=target_brand.name,
            product=ctx.product,
            competitors=[b.name for b in brand_rows if b.role == BrandRole.competitor],
            as_of_date=windows.as_of_date,
            period_days=windows.period_days,
            max_calls=ctx.serp_calls_budget,
        )
        budget = RunBudget(ctx.serp_calls_budget)
        with Session(engine) as session:
            analysis = session.get(Analysis, analysis_id)
            analysis.stage = "collecting"
            analysis.progress = 10
            session.commit()
        collected = fetcher.collect(
            plan, budget=budget, purpose=UsagePurpose.analysis, analysis_id=analysis_id
        )
        raw_repo = RawItemRepository(engine)
        for call, result in collected.fetched:
            parsed = parse_response(call.spec, result.response, result.cache_key)
            if parsed.items:
                brand_id = next(
                    b.id for b in brand_rows if b.name.casefold() == call.brand.casefold()
                )
                raw_repo.add_many(
                    RawItemContext(
                        analysis_id=analysis_id,
                        brand_id=brand_id,
                        purpose=ContentPurpose.collection,
                        window=call.window,
                        collected_at=cache._clock(),
                    ),
                    parsed.items,
                )
            if parsed.trends:
                _persist_trends(engine, analysis_id, brand_rows, parsed)
        with Session(engine) as session:
            analysis = session.get(Analysis, analysis_id)
            analysis.serp_calls_used = collected.live_calls
            analysis.live_run = collected.live_calls > 0
            analysis.warnings = [
                {"code": w.code, "message": w.message, "stage": "collecting"}
                for w in collected.warnings
            ]
            analysis.stage = "processing"
            analysis.progress = 35
            session.commit()
        raw_repo = RawItemRepository(engine)
        content_repo = ContentItemRepository(engine)
        process_result = __import__(
            "app.pipeline.process_raw_items", fromlist=["process_analysis_raw_items"]
        ).process_analysis_raw_items(
            raw_repo,
            content_repo,
            analysis_id,
            windows=windows,
            purpose=ContentPurpose.collection,
        )
        if process_result.inserted == 0:
            with Session(engine) as session:
                analysis = session.get(Analysis, analysis_id)
                warnings = list(analysis.warnings or [])
                warnings.append(
                    {
                        "code": "not_enough_data",
                        "message": "No usable content was collected; no signals can be produced.",
                        "stage": "processing",
                    }
                )
                analysis.warnings = warnings
                session.commit()
        with Session(engine) as session:
            analysis = session.get(Analysis, analysis_id)
            analysis.stage = "analyzing"
            analysis.progress = 55
            session.commit()
        analyzer = HFSentimentAnalyzer.from_settings(settings)
        for brand in brand_rows:
            _analyze_brand(
                engine,
                analysis_id,
                brand,
                ctx.category,
                analyzer,
                ctx.product,
            )
        with Session(engine) as session:
            analysis = session.get(Analysis, analysis_id)
            analysis.stage = "detecting"
            analysis.progress = 70
            session.commit()
        signal_repo = SignalRepository(engine)
        for brand in brand_rows:
            metric_rows = _metric_rows(engine, analysis_id, brand.id)
            aspects = sorted({m.aspect for m in metric_rows})
            corroborated = trend_corroborated(_interest_change(engine, ctx, brand))
            signals = []
            for aspect in aspects:
                candidate = detect_negative_spike(
                    metric_rows, aspect, trend_corroborated=corroborated
                )
                if candidate:
                    signals.append(
                        {
                            "analysis_id": analysis_id,
                            "brand_id": brand.id,
                            "kind": candidate.kind,
                            "aspect": candidate.aspect,
                            "baseline_n": candidate.baseline_n,
                            "baseline_total": candidate.baseline_total,
                            "current_n": candidate.current_n,
                            "current_total": candidate.current_total,
                            "baseline_share": candidate.baseline_share,
                            "current_share": candidate.current_share,
                            "growth": candidate.growth,
                            "components": candidate.components,
                            "signal_score": candidate.score,
                            "impact": candidate.impact,
                            "signal_confidence": candidate.confidence,
                            "sources_count": candidate.sources_count,
                            "source_types": list(candidate.source_types),
                            "trend_corroborated": corroborated,
                        }
                    )
            if signals:
                signal_repo.add_many(signals)
        with Session(engine) as session:
            analysis = session.get(Analysis, analysis_id)
            analysis.stage = "snapshotting"
            analysis.progress = 85
            session.commit()
        for brand in brand_rows:
            _snapshot(engine, ctx, brand)
        with Session(engine) as session:
            analysis = session.get(Analysis, analysis_id)
            analysis.stage = "done"
            analysis.progress = 100
            analysis.status = "completed" if not analysis.warnings else "partial"
            analysis.finished_at = datetime.now(UTC)
            session.commit()
    except Exception as exc:
        logger.exception(
            "analysis_pipeline_failed",
            extra={"analysis_id": str(analysis_id), "error_type": type(exc).__name__},
        )
        with Session(engine) as session:
            analysis = session.get(Analysis, analysis_id)
            if analysis:
                analysis.status = "failed"
                analysis.error = "Analysis failed. Check server logs for details."
                analysis.finished_at = datetime.now(UTC)
                session.commit()
