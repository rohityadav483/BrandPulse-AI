"""Validate the Phase 10 demo bundle against the public API schemas."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.schemas.api import DashboardResponse, EvidenceItem, InvestigationResponse, SignalDetail  # noqa: E402

BUNDLE = ROOT / "contracts" / "demo" / "samsung_s25_ultra.json"


def main() -> int:
    data = json.loads(BUNDLE.read_text(encoding="utf-8"))
    DashboardResponse.model_validate(data["dashboard"])
    SignalDetail.model_validate(data["signal_detail"])
    InvestigationResponse.model_validate(data["investigation"])
    for item in data["evidence"].get("items", []):
        EvidenceItem.model_validate(item)
    if data["meta"]["scenario"] != "Samsung Galaxy S25 Ultra":
        raise SystemExit("Unexpected demo scenario")
    print(f"Demo bundle valid: {BUNDLE}")
    print(f"Mode: {data['meta']['mode']}")
    print(f"Cache entries: {len(data.get('cache_entries', []))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
