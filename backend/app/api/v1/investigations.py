from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Path, Query
from sqlalchemy.orm import Session

from app.api.v1.deps import SettingsDep, error_responses
from app.api.v1.errors import ApiError
from app.db.models.investigation import Investigation
from app.db.repositories.investigation import (
    EvidenceRepository,
)
from app.db.session import get_engine
from app.schemas.api import *
from app.schemas.domain import (
    InvestigationStatus,
    InvestigationStep,
    SourceType,
    Stance,
    StepState,
)
from app.services.demo_bundle import is_demo_id, section

router = APIRouter(prefix="/investigations", tags=["investigations"])


def _dto(inv):
    return InvestigationResponse(
        id=inv.id,
        signal_id=inv.signal_id,
        analysis_id=inv.analysis_id,
        status=InvestigationStatus(inv.status),
        step=InvestigationStep(inv.step),
        steps=[
            InvestigationStepInfo(
                key=InvestigationStep(x["key"]),
                label=x["label"],
                state=StepState(x["state"]),
            )
            for x in inv.steps
        ],
        report=inv.report,
        error=inv.error,
    )


@router.get(
    "/{id}",
    response_model=InvestigationResponse,
    operation_id="getInvestigation",
    responses=error_responses(404, 422),
)
def get_investigation(id: Annotated[str, Path()], settings: SettingsDep):
    if settings.demo_mode and is_demo_id(id):
        return InvestigationResponse.model_validate(section("investigation"))
    try:
        iid = UUID(id)
    except ValueError:
        raise ApiError(404, "not_found", "Unknown investigation ID.")
    with Session(
        get_engine(settings.database_url or settings.database_url_direct)
    ) as s:
        inv = s.get(Investigation, iid)
    if not inv:
        raise ApiError(404, "not_found", "Unknown investigation ID.")
    return _dto(inv)


@router.get(
    "/{id}/evidence",
    response_model=ListEvidenceResponse,
    operation_id="listInvestigationEvidence",
    responses=error_responses(404, 422),
)
def list_investigation_evidence(
    id: Annotated[str, Path()],
    settings: SettingsDep,
    stance: Stance | None = None,
    source_type: SourceType | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
):
    if settings.demo_mode and is_demo_id(id):
        return ListEvidenceResponse.model_validate(section("evidence"))
    try:
        iid = UUID(id)
    except ValueError:
        raise ApiError(404, "not_found", "Unknown investigation ID.")
    with Session(
        get_engine(settings.database_url or settings.database_url_direct)
    ) as s:
        if not s.get(Investigation, iid):
            raise ApiError(404, "not_found", "Unknown investigation ID.")
    rows, total, counts = EvidenceRepository(
        get_engine(settings.database_url or settings.database_url_direct)
    ).list(iid, stance=stance, source_type=source_type, page=page, page_size=page_size)
    with Session(
        get_engine(settings.database_url or settings.database_url_direct)
    ) as s:
        from app.db.models.content_item import ContentItemRow

        out = []
        for e in rows:
            c = s.get(ContentItemRow, e.content_id)
            out.append(
                EvidenceItem(
                    id=e.id,
                    stance=Stance(e.stance),
                    relevance=e.relevance,
                    note=e.note,
                    rank=e.rank,
                    source=Source(
                        source_type=c.source_type,
                        domain=c.domain,
                        url=c.url,
                        title=c.title,
                        snippet=c.snippet,
                        author=c.author,
                        published_at=c.published_at,
                        date_confidence=c.date_confidence,
                        collected_at=c.collected_at,
                    ),
                )
            )
    return ListEvidenceResponse(
        items=out,
        page=page,
        page_size=page_size,
        total=total,
        counts=EvidenceCounts(**counts),
    )
