from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Header, Path, Query, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.analyses import _engine, _ip_hash, _quota, _rate_ok
from app.api.v1.deps import SettingsDep, error_responses
from app.api.v1.errors import ApiError
from app.db.models.analysis import Analysis, AnalysisBrand
from app.db.models.brand import Brand
from app.db.models.enums import AnalysisStatus, SignalStatus
from app.db.models.investigation import Investigation
from app.db.models.phase5 import Signal
from app.pipeline.jobs import reap_stale_jobs_safe, start_investigation_job
from app.schemas.api import (
    BrandRef,
    InvestigateSignalResponse,
    InvestigationRef,
    ScoreComponents,
    SignalDetail,
)
from app.schemas.domain import BrandRole, ConfidenceSource, InvestigationStatus
from app.services.demo_bundle import DEMO_INVESTIGATION_ID, is_demo_id, section

router = APIRouter(prefix="/signals", tags=["signals"])
SignalId = Annotated[str, Path()]


@router.get(
    "/{id}",
    response_model=SignalDetail,
    operation_id="getSignal",
    responses=error_responses(404, 422, 501),
)
def get_signal(id: SignalId, settings: SettingsDep) -> SignalDetail:
    if settings.demo_mode and is_demo_id(id):
        return SignalDetail.model_validate(section("signal_detail"))
    try:
        sid = UUID(id)
    except ValueError:
        raise ApiError(404, "not_found", "Unknown signal ID.")
    with Session(_engine(settings)) as s:
        sig = s.get(Signal, sid)
        if not sig:
            raise ApiError(404, "not_found", "Unknown signal ID.")
        brand = s.get(Brand, sig.brand_id)
        if not brand:
            raise ApiError(404, "not_found", "Signal brand not found.")
        link = s.get(AnalysisBrand, (sig.analysis_id, sig.brand_id))
        if link is None:
            raise ApiError(404, "not_found", "Signal brand not found.")
        latest = s.scalars(
            select(Investigation)
            .where(Investigation.signal_id == sig.id)
            .order_by(Investigation.created_at.desc(), Investigation.id.desc())
            .limit(1)
        ).first()
        return SignalDetail(
            id=sig.id,
            kind=sig.kind,
            aspect=sig.aspect,
            growth=sig.growth,
            impact=sig.impact,
            confidence=sig.signal_confidence,
            confidence_source=ConfidenceSource.signal,
            sources_count=sig.sources_count,
            source_types=sig.source_types,
            current_share=sig.current_share,
            baseline_share=sig.baseline_share,
            current_n=sig.current_n,
            baseline_n=sig.baseline_n,
            trend_corroborated=sig.trend_corroborated,
            status=sig.status,
            analysis_id=sig.analysis_id,
            brand=BrandRef(id=brand.id, name=brand.name, role=BrandRole(link.role.value)),
            score=sig.signal_score,
            score_components=ScoreComponents(**sig.components),
            latest_investigation=(
                InvestigationRef(id=latest.id, status=InvestigationStatus(latest.status))
                if latest
                else None
            ),
        )


@router.post(
    "/{id}/investigate",
    response_model=InvestigateSignalResponse,
    status_code=202,
    operation_id="investigateSignal",
    responses={
        200: {
            "model": InvestigateSignalResponse,
            "description": "Existing investigation reused",
        },
        **error_responses(403, 404, 409, 422, 429, 501),
    },
)
def investigate_signal(
    id: SignalId,
    request: Request,
    response: Response,
    background_tasks: BackgroundTasks,
    settings: SettingsDep,
    force: bool = Query(False),
    x_access_code: Annotated[str | None, Header(alias="X-Access-Code")] = None,
) -> InvestigateSignalResponse:
    # API.md 3.7. Order: demo -> 404 -> 501 -> 429 rate limit -> 409 not investigable ->
    # reuse (200) or 409 in progress -> 403 access code -> 429 quota -> create (202).
    # (A comment, not a docstring: a docstring would change contracts/openapi.json.)
    # The signal row is locked while deciding, so concurrent calls cannot create two.
    if settings.demo_mode and is_demo_id(id):
        response.status_code = 200
        return InvestigateSignalResponse(
            investigation_id=UUID(DEMO_INVESTIGATION_ID),
            status=InvestigationStatus.completed,
            reused=True,
            poll_url=f"/api/v1/investigations/{DEMO_INVESTIGATION_ID}",
        )
    try:
        sid = UUID(id)
    except ValueError:
        raise ApiError(404, "not_found", "Unknown signal ID.")
    engine = _engine(settings)
    with Session(engine) as s:
        if s.get(Signal, sid) is None:
            raise ApiError(404, "not_found", "Unknown signal ID.")
    if not _rate_ok("investigate:" + _ip_hash(request)):
        raise ApiError(429, "rate_limited", "Too many investigation requests.")
    reap_stale_jobs_safe(settings)

    with Session(engine) as s, s.begin():
        # Row lock = single-flight guard: a concurrent call waits here, then sees our row.
        sig = s.scalar(select(Signal).where(Signal.id == sid).with_for_update())
        if sig is None:
            raise ApiError(404, "not_found", "Unknown signal ID.")
        analysis = s.get(Analysis, sig.analysis_id)
        if analysis is None or analysis.status not in (
            AnalysisStatus.completed,
            AnalysisStatus.partial,
        ):
            raise ApiError(
                409,
                "signal_not_investigable",
                "The analysis for this signal has not finished.",
            )
        rows = s.scalars(
            select(Investigation)
            .where(Investigation.signal_id == sid)
            .order_by(Investigation.created_at.desc(), Investigation.id.desc())
        ).all()
        active = next((r for r in rows if r.status in ("queued", "running")), None)
        completed = next((r for r in rows if r.status == "completed"), None)
        if active is not None:
            if force:
                raise ApiError(
                    409,
                    "investigation_in_progress",
                    "An investigation for this signal is already running.",
                )
            reuse = active
        elif completed is not None and not force:
            reuse = completed
        else:
            reuse = None  # none yet, only failed ones, or force=true over a completed one
        if reuse is not None:
            response.status_code = 200
            return InvestigateSignalResponse(
                investigation_id=reuse.id,
                status=InvestigationStatus(reuse.status),
                reused=True,
                poll_url=f"/api/v1/investigations/{reuse.id}",
            )

        # A new investigation may spend SerpApi credits: enforce the live-access rules.
        code = settings.live_access_code.get_secret_value()
        if settings.allow_live_serpapi and settings.serp_budget_per_investigation > 0:
            if not code or x_access_code != code:
                raise ApiError(
                    403,
                    "live_access_required",
                    "A valid X-Access-Code is required for new live searches.",
                )
            quota = _quota(settings).snapshot()
            need = settings.serp_budget_per_investigation
            if quota.remaining - need < quota.reserve:
                raise ApiError(
                    429, "serpapi_quota_low", "Not enough SerpApi quota left."
                )

        inv = Investigation(signal_id=sig.id, analysis_id=sig.analysis_id)
        s.add(inv)
        sig.status = SignalStatus.investigating
        s.flush()
        investigation_id = inv.id

    background_tasks.add_task(start_investigation_job, investigation_id, settings)
    return InvestigateSignalResponse(
        investigation_id=investigation_id,
        status=InvestigationStatus.queued,
        reused=False,
        poll_url=f"/api/v1/investigations/{investigation_id}",
    )
