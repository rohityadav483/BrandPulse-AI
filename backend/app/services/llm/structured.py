import json
from typing import Any


def parse_json_object(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:].strip()
    value = json.loads(text)
    if not isinstance(value, dict):
        raise TypeError("LLM output must be a JSON object")
    return value
