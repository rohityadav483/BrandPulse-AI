"""Analysis endpoints (API.md section 3.1-3.5, 3.11).

Contract stubs: request/response shapes and OpenAPI are real, behavior is not. Every route
answers 501 `not_implemented` until the pipeline lands (Phase 6).
"""

from typing import Annotated, NoReturn
from uuid import UUID

from fastapi import APIRouter, Header, Path, Query

from app.api.v1.deps import error_responses
from app.api.v1.errors import ApiError
from app.schemas.api import (
    AnalysisStatusResponse,
    CreateAnalysisRequest,
    CreateAnalysisResponse,
    DashboardResponse,
    EstimateAnalysisResponse,
    ListAnalysesResponse,
    ListMentionsResponse,
)
from app.schemas.domain import Sentiment, SourceType, WindowKind

router = APIRouter(prefix="/analyses", tags=["analyses"])

AnalysisId = Annotated[
    str, Path(description="Analysis UUID (or a demo alias when DEMO_MODE=true).")
]
AccessCode = Annotated[
    str | None,
    Header(
        alias="X-Access-Code",
        description="Required only when the run needs new SerpApi calls (LIVE_ACCESS_CODE set).",
    ),
]


def _not_implemented() -> NoReturn:
    raise ApiError(501, "not_implemented", "This endpoint is not implemented yet.")


@router.post(
    "/estimate",
    response_model=EstimateAnalysisResponse,
    operation_id="estimateAnalysis",
    summary="Cost preview; no side effects",
    responses=error_responses(400, 422, 501),
)
def estimate_analysis(body: CreateAnalysisRequest) -> NoReturn:
    _not_implemented()


@router.post(
    "",
    response_model=CreateAnalysisResponse,
    status_code=202,
    operation_id="createAnalysis",
    summary="Start an analysis",
    responses=error_responses(400, 403, 409, 422, 429, 501, 503),
)
def create_analysis(body: CreateAnalysisRequest, x_access_code: AccessCode = None) -> NoReturn:
    _not_implemented()


@router.get(
    "",
    response_model=ListAnalysesResponse,
    operation_id="listAnalyses",
    summary="Recent analyses",
    responses=error_responses(422, 501),
)
def list_analyses(limit: Annotated[int, Query(ge=1, le=50)] = 10) -> NoReturn:
    _not_implemented()


@router.get(
    "/{id}",
    response_model=AnalysisStatusResponse,
    operation_id="getAnalysis",
    summary="Status, stage, progress",
    responses=error_responses(404, 422, 501),
)
def get_analysis(id: AnalysisId) -> NoReturn:
    _not_implemented()


@router.get(
    "/{id}/dashboard",
    response_model=DashboardResponse,
    operation_id="getDashboard",
    summary="Full dashboard payload",
    responses=error_responses(404, 409, 422, 501),
)
def get_dashboard(id: AnalysisId) -> NoReturn:
    _not_implemented()


@router.get(
    "/{id}/mentions",
    response_model=ListMentionsResponse,
    operation_id="listMentions",
    summary="Source items behind an aspect or sentiment",
    responses=error_responses(404, 422, 501),
)
def list_mentions(
    id: AnalysisId,
    brand_id: Annotated[UUID | None, Query(description="Default: the target brand.")] = None,
    aspect: Annotated[str | None, Query(description="e.g. `battery`.")] = None,
    sentiment: Sentiment | None = None,
    source_type: SourceType | None = None,
    window: WindowKind = WindowKind.current,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> NoReturn:
    _not_implemented()
