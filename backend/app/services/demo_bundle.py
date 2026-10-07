"""Read-only Phase 10 demo bundle support.

The bundle is intentionally file-backed so the fallback path works without PostgreSQL,
SerpApi, Groq, or the local sentiment model.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
BUNDLE_PATH = ROOT / "contracts" / "demo" / "samsung_s25_ultra.json"
DEMO_ANALYSIS_ID = "00000000-0000-4000-8000-000000000001"
DEMO_SIGNAL_ID = "00000000-0000-4000-8000-000000000020"
DEMO_INVESTIGATION_ID = "00000000-0000-4000-8000-000000000030"


@lru_cache(maxsize=1)
def load_demo_bundle() -> dict[str, Any]:
    if not BUNDLE_PATH.exists():
        raise FileNotFoundError(f"Demo bundle not found: {BUNDLE_PATH}")
    with BUNDLE_PATH.open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise TypeError("Demo bundle root must be an object")
    return value


def is_demo_id(value: str) -> bool:
    return value in {
        "demo",
        DEMO_ANALYSIS_ID,
        DEMO_SIGNAL_ID,
        DEMO_INVESTIGATION_ID,
        "demo-signal-battery",
        "demo-investigation",
    }


def section(name: str) -> dict[str, Any]:
    value = load_demo_bundle().get(name)
    if not isinstance(value, dict):
        raise TypeError(f"Demo bundle section '{name}' is missing")
    return value
