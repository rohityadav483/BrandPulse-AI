from pathlib import Path

from app.schemas.api import (
    DashboardResponse,
    EvidenceItem,
    InvestigationResponse,
    SignalDetail,
)
from app.services.demo_bundle import (
    BUNDLE_PATH,
    DEMO_ANALYSIS_ID,
    DEMO_INVESTIGATION_ID,
    DEMO_SIGNAL_ID,
    is_demo_id,
    load_demo_bundle,
)


def test_demo_bundle_exists_and_matches_public_contracts():
    assert Path(BUNDLE_PATH).exists()
    data = load_demo_bundle()
    DashboardResponse.model_validate(data["dashboard"])
    SignalDetail.model_validate(data["signal_detail"])
    InvestigationResponse.model_validate(data["investigation"])
    for item in data["evidence"]["items"]:
        EvidenceItem.model_validate(item)


def test_demo_aliases_are_stable():
    assert all(
        is_demo_id(value)
        for value in ("demo", DEMO_ANALYSIS_ID, DEMO_SIGNAL_ID, DEMO_INVESTIGATION_ID)
    )
    assert not is_demo_id("00000000-0000-4000-8000-000000000099")
