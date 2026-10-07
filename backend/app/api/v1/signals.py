from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, Path, Query
from sqlalchemy.orm import Session

from app.api.v1.deps import SettingsDep, error_responses
from app.api.v1.errors import ApiError
from app.db.models.brand import Brand
from app.db.models.investigation import Investigation
from app.db.models.phase5 import Signal
from app.db.session import get_engine
from app.pipeline.investigation_pipeline import run_investigation
from app.schemas.api import (
    BrandRef,
    InvestigateSignalResponse,
    ScoreComponents,
    SignalDetail,
)
from app.schemas.domain import BrandRole, ConfidenceSource, InvestigationStatus
from app.services.demo_bundle import is_demo_id, section

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
    with Session(
        get_engine(settings.database_url or settings.database_url_direct)
    ) as s:
        sig = s.get(Signal, sid)
        if not sig:
            raise ApiError(404, "not_found", "Unknown signal ID.")
        brand = s.get(Brand, sig.brand_id)
        if not brand:
            raise ApiError(404, "not_found", "Signal brand not found.")
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
            brand=BrandRef(id=brand.id, name=brand.name, role=BrandRole.target),
            score=sig.signal_score,
            score_components=ScoreComponents(**sig.components),
            latest_investigation=None,
        )


@router.post(
    "/{id}/investigate",
    response_model=__import__(
        "app.schemas.api", fromlist=["InvestigateSignalResponse"]
    ).InvestigateSignalResponse,
    status_code=202,
    operation_id="investigateSignal",
    responses={
        200: {
            "model": __import__(
                "app.schemas.api", fromlist=["InvestigateSignalResponse"]
            ).InvestigateSignalResponse,
            "description": "Existing investigation reused",
        },
        **error_responses(403, 404, 409, 422, 429, 501),
    },
)
def investigate_signal(
    id: SignalId,
    settings: SettingsDep,
    force: bool = Query(False),
    x_access_code: Annotated[str | None, Header(alias="X-Access-Code")] = None,
):
    try:
        sid = UUID(id)
    except ValueError:
        raise ApiError(404, "not_found", "Unknown signal ID.")
    engine = get_engine(settings.database_url or settings.database_url_direct)
    with Session(engine) as s:
        sig = s.get(Signal, sid)
        if not sig:
            raise ApiError(404, "not_found", "Unknown signal ID.")
        existing = (
            s.query(Investigation)
            .filter_by(signal_id=sid)
            .order_by(Investigation.created_at.desc())
            .first()
        )
        if existing and not force:
            return InvestigateSignalResponse(
                investigation_id=existing.id,
                status=InvestigationStatus(existing.status),
                reused=True,
                poll_url=f"/api/v1/investigations/{existing.id}",
            )
        inv = Investigation(signal_id=sig.id, analysis_id=sig.analysis_id)
        s.add(inv)
        s.commit()
        s.refresh(inv)

    # BackgroundTasks is injected by FastAPI only if declared; use the app's thread runner through direct task dispatch below.
    import threading

    threading.Thread(
        target=run_investigation, args=(inv.id, settings), daemon=True
    ).start()
    return InvestigateSignalResponse(
        investigation_id=inv.id,
        status=InvestigationStatus.queued,
        reused=False,
        poll_url=f"/api/v1/investigations/{inv.id}",
    )
