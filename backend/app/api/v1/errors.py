"""Standard error envelope (API.md §1): every non-2xx response is `{"error": {...}}`."""

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.schemas.api import ErrorBody, ErrorResponse


class ApiError(Exception):
    """Raise from routers/pipeline to return a typed error envelope."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or {}
        self.headers = headers


def error_response(
    status_code: int,
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    body = ErrorResponse(error=ErrorBody(code=code, message=message, details=details or {}))
    return JSONResponse(status_code=status_code, content=body.model_dump(), headers=headers)


def _code_for_status(status_code: int) -> str:
    if status_code == 404:
        return "not_found"
    if status_code == 405:
        return "method_not_allowed"
    if status_code >= 500:
        return "internal_error"
    return "bad_request"


async def _handle_api_error(request: Request, exc: ApiError) -> JSONResponse:
    return error_response(exc.status_code, exc.code, exc.message, exc.details, exc.headers)


async def _handle_http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    if exc.status_code == 404:
        message = "Resource not found."
    elif isinstance(exc.detail, str) and exc.status_code < 500:
        message = exc.detail
    else:
        message = "Request failed."
    return error_response(
        exc.status_code, _code_for_status(exc.status_code), message, headers=exc.headers
    )


async def _handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    errors = exc.errors()
    if any(e.get("type") == "json_invalid" for e in errors):
        return error_response(400, "bad_request", "Malformed request body.")
    # Never echo the submitted input back; only the field path and the message.
    fields = [
        {
            "field": ".".join(str(part) for part in e["loc"] if part not in ("body", "query")),
            "message": e["msg"],
        }
        for e in errors
    ]
    return error_response(422, "validation_error", "Request validation failed.", {"fields": fields})


async def _handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
    # The exception itself is logged by the request-logging middleware. Never leak internals.
    return error_response(500, "internal_error", "An unexpected error occurred.")


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ApiError, _handle_api_error)
    app.add_exception_handler(StarletteHTTPException, _handle_http_exception)
    app.add_exception_handler(RequestValidationError, _handle_validation_error)
    app.add_exception_handler(Exception, _handle_unexpected)
