"""Investigation endpoints (API.md section 3.8, 3.9). Contract stubs: 501 until Phase 7."""

from typing import Annotated, NoReturn

from fastapi import APIRouter, Path, Query

from app.api.v1.deps import error_responses
from app.api.v1.errors import ApiError
from app.schemas.api import InvestigationResponse, ListEvidenceResponse
from app.schemas.domain import SourceType, Stance

router = APIRouter(prefix="/investigations", tags=["investigations"])

InvestigationId = Annotated[
    str, Path(description="Investigation UUID (or a demo alias when DEMO_MODE=true).")
]


def _not_implemented() -> NoReturn:
    raise ApiError(501, "not_implemented", "This endpoint is not implemented yet.")


@router.get(
    "/{id}",
    response_model=InvestigationResponse,
    operation_id="getInvestigation",
    summary="Status, then full report",
    responses=error_responses(404, 422, 501),
)
def get_investigation(id: InvestigationId) -> NoReturn:
    _not_implemented()


@router.get(
    "/{id}/evidence",
    response_model=ListEvidenceResponse,
    operation_id="listInvestigationEvidence",
    summary="Evidence explorer",
    responses=error_responses(404, 422, 501),
)
def list_investigation_evidence(
    id: InvestigationId,
    stance: Stance | None = None,
    source_type: SourceType | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> NoReturn:
    _not_implemented()
