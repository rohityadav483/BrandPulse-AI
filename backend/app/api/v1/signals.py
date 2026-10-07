"""Signal endpoints (API.md section 3.6, 3.7). Contract stubs: 501 until Phase 5/7."""

from typing import Annotated, NoReturn

from fastapi import APIRouter, Header, Path, Query

from app.api.v1.deps import error_responses
from app.api.v1.errors import ApiError
from app.schemas.api import InvestigateSignalResponse, SignalDetail

router = APIRouter(prefix="/signals", tags=["signals"])

SignalId = Annotated[str, Path(description="Signal UUID (or a demo alias when DEMO_MODE=true).")]


def _not_implemented() -> NoReturn:
    raise ApiError(501, "not_implemented", "This endpoint is not implemented yet.")


@router.get(
    "/{id}",
    response_model=SignalDetail,
    operation_id="getSignal",
    summary="Signal detail",
    responses=error_responses(404, 422, 501),
)
def get_signal(id: SignalId) -> NoReturn:
    _not_implemented()


@router.post(
    "/{id}/investigate",
    response_model=InvestigateSignalResponse,
    status_code=202,
    operation_id="investigateSignal",
    summary="Start or reuse an investigation (idempotent by default)",
    description=(
        "`202` when a new investigation is created. `200` with `reused: true` when a queued, "
        "running or completed investigation already exists and `force` is false."
    ),
    responses={
        200: {
            "model": InvestigateSignalResponse,
            "description": "Existing investigation reused (`reused: true`).",
        },
        **error_responses(403, 404, 409, 422, 429, 501),
    },
)
def investigate_signal(
    id: SignalId,
    force: Annotated[
        bool, Query(description="Start a new investigation even if a completed one exists.")
    ] = False,
    x_access_code: Annotated[
        str | None,
        Header(alias="X-Access-Code", description="Only when new SerpApi calls are needed"),
    ] = None,
) -> NoReturn:
    _not_implemented()
