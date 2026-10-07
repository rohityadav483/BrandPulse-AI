import json
from pathlib import Path

import pytest

from app.config.scoring_config import (
    growth_ratio,
    health_score,
    investigation_confidence,
    net_score,
    signal_score,
)
from app.schemas.api import (
    DashboardResponse,
    InvestigationResponse,
    ListEvidenceResponse,
    SignalDetail,
)

FIXTURE = (
    Path(__file__).resolve().parents[2] / ".." / "contracts" / "golden" / "samsung_battery.json"
)


@pytest.fixture(scope="module")
def golden():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_golden_sections_validate_against_api_models(golden):
    assert DashboardResponse.model_validate(golden["dashboard"])
    assert SignalDetail.model_validate(golden["signal_detail"])
    assert InvestigationResponse.model_validate(golden["investigation"])
    assert ListEvidenceResponse.model_validate(golden["evidence"])


def test_golden_growth_formula(golden):
    f = golden["formula_inputs"]["growth"]
    actual = growth_ratio(
        f["current_n"], f["current_N"], f["baseline_n"], f["baseline_N"], f["epsilon"]
    )
    assert actual == pytest.approx(f["expected"], abs=0.02)


def test_golden_signal_score_formula(golden):
    f = golden["formula_inputs"]["signal"]
    actual = signal_score(
        f["growth_component"],
        f["frequency_component"],
        f["cross_source_component"],
        f["sentiment_impact_component"],
    )
    assert round(actual, 2) == f["expected_score"]


def test_golden_health_formula(golden):
    f = golden["formula_inputs"]["health"]
    assert (
        health_score(f["sentiment"], f["engagement"], f["risk"], f["trend"])
        == f["expected_overall"]
    )


def test_golden_investigation_confidence_formula(golden):
    f = golden["formula_inputs"]["confidence"]
    assert (
        investigation_confidence(
            f["independence"], f["agreement"], f["signal_strength"], f["recency"], f["consistency"]
        )
        == f["expected_score"]
    )


def test_golden_net_scores(golden):
    for f in golden["formula_inputs"]["net_scores"].values():
        assert net_score(f["positive"], f["negative"]) == f["expected"]


def test_invalid_golden_growth_inputs_are_rejected():
    with pytest.raises(ValueError):
        growth_ratio(4, 3, 1, 10)
