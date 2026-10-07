"""Validate the Phase 0 golden fixture against API DTOs."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

FIXTURE = ROOT / "contracts" / "golden" / "samsung_battery.json"


def main() -> None:
    from app.schemas.api import (
        DashboardResponse,
        InvestigationResponse,
        ListEvidenceResponse,
        SignalDetail,
    )

    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    DashboardResponse.model_validate(data["dashboard"])
    SignalDetail.model_validate(data["signal_detail"])
    InvestigationResponse.model_validate(data["investigation"])
    ListEvidenceResponse.model_validate(data["evidence"])
    print(
        "Golden fixture is valid against DashboardResponse, SignalDetail, "
        "InvestigationResponse and ListEvidenceResponse."
    )


if __name__ == "__main__":
    main()
