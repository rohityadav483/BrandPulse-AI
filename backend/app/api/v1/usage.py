"""GET /api/v1/usage (API.md section 3.12). Contract stub: 501 until Phase 2/6."""

from typing import NoReturn

from fastapi import APIRouter

from app.api.v1.deps import error_responses
from app.api.v1.errors import ApiError
from app.schemas.api import UsageResponse

router = APIRouter(tags=["usage"])


@router.get(
    "/usage",
    response_model=UsageResponse,
    operation_id="getUsage",
    summary="Monthly SerpApi and daily Groq/analysis usage",
    responses=error_responses(501),
)
def get_usage() -> NoReturn:
    raise ApiError(501, "not_implemented", "This endpoint is not implemented yet.")
