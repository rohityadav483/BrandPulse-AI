"""Structured (JSON) logging using only the standard library."""

import json
import logging
import re
import sys
from contextvars import ContextVar
from datetime import UTC, datetime

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)

# Attributes present on every LogRecord; anything else came from `extra=`.
_STANDARD_ATTRS = set(vars(logging.makeLogRecord({}))) | {
    "message",
    "asctime",
    "request_id",
    "color_message",
}


_SENSITIVE = ("api_key", "access_code", "authorization", "password", "secret", "token")
_URL_PASSWORD = re.compile(r"(://[^:/@\s]+:)([^@/\s]+)(@)")


def _safe_log_value(key: str, value: object) -> object:
    if any(part in key.casefold() for part in _SENSITIVE):
        return "[REDACTED]"
    if isinstance(value, str):
        value = _URL_PASSWORD.sub(r"\1[REDACTED]\3", value)
    if isinstance(value, dict):
        return {str(k): _safe_log_value(str(k), v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe_log_value(key, v) for v in value]
    return value


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        request_id = getattr(record, "request_id", None)
        if request_id:
            payload["request_id"] = request_id
        for key, value in record.__dict__.items():
            if key not in _STANDARD_ATTRS and not key.startswith("_"):
                payload[key] = _safe_log_value(key, value)
        if record.exc_info:
            payload["exception"] = _safe_log_value(
                "exception", self.formatException(record.exc_info)
            )
        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO") -> None:
    """Route all logging to stdout as JSON. Safe to call more than once."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(RequestIdFilter())

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)

    # Let uvicorn records flow through the root handler. Request access is logged by our
    # middleware, so silence uvicorn's own access log to avoid duplicates.
    for name in ("uvicorn", "uvicorn.error"):
        lg = logging.getLogger(name)
        lg.handlers = []
        lg.propagate = True
    access = logging.getLogger("uvicorn.access")
    access.handlers = []
    access.propagate = False
