"""Shared FastAPI dependencies."""

from typing import Annotated, Any

from fastapi import Depends, Request

from app.config.settings import Settings
from app.schemas.api import ErrorResponse


def get_app_settings(request: Request) -> Settings:
    return request.app.state.settings


SettingsDep = Annotated[Settings, Depends(get_app_settings)]


_ERROR_DESCRIPTIONS = {
    400: "bad_request: malformed body.",
    403: "live_access_required: new SerpApi calls needed; `X-Access-Code` missing or wrong.",
    404: "not_found: unknown or deleted ID.",
    409: (
        "analysis_not_ready, analysis_failed, signal_not_investigable, "
        "investigation_in_progress or live_data_disabled."
    ),
    422: "validation_error: field validation failed (`details.fields`).",
    429: "daily_limit_reached, rate_limited (`Retry-After` set) or serpapi_quota_low.",
    501: "not_implemented: route is a contract stub until its phase lands.",
    503: "nlp_unavailable or service_unavailable.",
}


def error_responses(*status_codes: int) -> dict[int | str, dict[str, Any]]:
    """OpenAPI `responses` entries that document the shared error envelope (API.md section 1)."""
    return {
        code: {"model": ErrorResponse, "description": _ERROR_DESCRIPTIONS[code]}
        for code in status_codes
    }
