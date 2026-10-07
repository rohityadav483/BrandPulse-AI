"""Strip the API key from anything that may be stored, logged or committed.

SerpApi echoes request parameters in some responses and in pagination links, so every response
passes through `sanitize_response` before it is cached or written as a fixture.
"""

import re
from typing import Any

_API_KEY_IN_TEXT = re.compile(r"(api_key=)[^&\s\"'<>]+", re.IGNORECASE)

REDACTED = "REDACTED"


def redact_text(text: str) -> str:
    """Replace the value of any `api_key=...` query parameter inside a string."""
    return _API_KEY_IN_TEXT.sub(rf"\1{REDACTED}", text)


def sanitize_response(value: Any) -> Any:
    """Deep copy of `value` without `api_key` keys and with `api_key=` values redacted."""
    if isinstance(value, dict):
        return {
            key: sanitize_response(item)
            for key, item in value.items()
            if str(key).lower() != "api_key"
        }
    if isinstance(value, list):
        return [sanitize_response(item) for item in value]
    if isinstance(value, str):
        return redact_text(value)
    return value
