import json
import logging

from app.utils.logging_config import (
    JsonFormatter,
    RequestIdFilter,
    configure_logging,
    request_id_var,
)


def _record(msg="hello", **extra) -> logging.LogRecord:
    record = logging.LogRecord("t", logging.INFO, __file__, 1, msg, None, None)
    for key, value in extra.items():
        setattr(record, key, value)
    RequestIdFilter().filter(record)
    return record


def test_formats_valid_json_with_extras():
    out = json.loads(JsonFormatter().format(_record("hi", status=200, path="/x")))
    assert out["message"] == "hi"
    assert out["level"] == "INFO"
    assert out["logger"] == "t"
    assert out["status"] == 200 and out["path"] == "/x"
    assert "ts" in out and "request_id" not in out


def test_includes_request_id_when_set():
    token = request_id_var.set("abc123")
    try:
        out = json.loads(JsonFormatter().format(_record()))
    finally:
        request_id_var.reset(token)
    assert out["request_id"] == "abc123"


def test_includes_exception_text():
    try:
        raise ValueError("boom")
    except ValueError:
        import sys

        record = _record()
        record.exc_info = sys.exc_info()
    out = json.loads(JsonFormatter().format(record))
    assert "ValueError: boom" in out["exception"]


def test_configure_logging_is_idempotent_and_sets_level():
    configure_logging("WARNING")
    configure_logging("DEBUG")
    root = logging.getLogger()
    assert len(root.handlers) == 1
    assert root.level == logging.DEBUG
    assert isinstance(root.handlers[0].formatter, JsonFormatter)


def test_uvicorn_color_message_is_not_emitted():
    out = json.loads(
        JsonFormatter().format(_record("Started", color_message="\x1b[36mx"))
    )
    assert "color_message" not in out
