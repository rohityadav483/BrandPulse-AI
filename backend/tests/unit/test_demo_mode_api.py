"""DEMO_MODE=true with no database, no model and no network: every documented demo route works.

Covers the routes that used to fail without a database: `GET /analyses/demo/mentions` (404),
`GET /usage` (501), `POST /analyses/estimate` (501) and `POST /signals/{demo}/investigate`
(404). Also checks that demo ids are NOT special when DEMO_MODE is off.
"""

import pytest

from app.schemas.api import (
    DashboardResponse,
    EstimateAnalysisResponse,
    EvidenceItem,
    InvestigateSignalResponse,
    InvestigationResponse,
    ListEvidenceResponse,
    ListMentionsResponse,
    SignalDetail,
    UsageResponse,
)
from app.services.demo_bundle import (
    DEMO_ANALYSIS_ID,
    DEMO_INVESTIGATION_ID,
    DEMO_SIGNAL_ID,
)

P = "/api/v1"
ESTIMATE_BODY = {
    "brand": "Samsung",
    "product": "Galaxy S25 Ultra",
    "competitors": ["Apple", "OnePlus"],
    "period_days": 30,
    "as_of_date": "2026-08-10",
}


@pytest.fixture
def client(make_client):
    return make_client(demo_mode=True)  # no DATABASE_URL, no keys


@pytest.mark.parametrize("alias", ["demo", DEMO_ANALYSIS_ID])
def test_analysis_status_and_dashboard(client, alias):
    assert client.get(f"{P}/analyses/{alias}").status_code == 200
    res = client.get(f"{P}/analyses/{alias}/dashboard")
    assert res.status_code == 200, res.text
    body = DashboardResponse.model_validate(res.json())
    assert body.target.brand.role.value == "target"


@pytest.mark.parametrize("alias", ["demo", DEMO_ANALYSIS_ID])
def test_mentions_served_from_bundle(client, alias):
    res = client.get(f"{P}/analyses/{alias}/mentions")
    assert res.status_code == 200, res.text
    body = ListMentionsResponse.model_validate(res.json())
    assert body.total >= 1 and body.page == 1 and body.page_size == 20
    assert all(m.aspects and m.aspects[0].aspect == "battery" for m in body.items)


def test_mentions_filters_and_paging(client):
    everything = client.get(f"{P}/analyses/demo/mentions").json()["total"]
    page = client.get(f"{P}/analyses/demo/mentions?page=1&page_size=1").json()
    assert page["total"] == everything and len(page["items"]) == 1
    past_end = client.get(f"{P}/analyses/demo/mentions?page=99").json()
    assert past_end["items"] == [] and past_end["total"] == everything
    assert client.get(f"{P}/analyses/demo/mentions?aspect=battery").json()["total"] == everything
    assert client.get(f"{P}/analyses/demo/mentions?aspect=camera").json()["total"] == 0
    assert client.get(f"{P}/analyses/demo/mentions?sentiment=positive").json()["total"] == 0
    assert (
        client.get(f"{P}/analyses/demo/mentions?source_type=forum").json()["total"] >= 1
    )
    other_brand = "00000000-0000-4000-8000-0000000000ff"
    assert client.get(f"{P}/analyses/demo/mentions?brand_id={other_brand}").json()["total"] == 0


def test_mentions_validate_query_parameters(client):
    assert client.get(f"{P}/analyses/demo/mentions?page=0").status_code == 422
    assert client.get(f"{P}/analyses/demo/mentions?page_size=101").status_code == 422


def test_usage_without_database(client):
    res = client.get(f"{P}/usage")
    assert res.status_code == 200, res.text
    body = UsageResponse.model_validate(res.json())
    assert body.serpapi.used == 0
    assert body.serpapi.remaining == body.serpapi.limit
    assert body.serpapi.live_enabled is False
    assert body.groq.configured is False
    assert body.analyses_today.used == 0


def test_estimate_without_database(client):
    res = client.post(f"{P}/analyses/estimate", json=ESTIMATE_BODY)
    assert res.status_code == 200, res.text
    body = EstimateAnalysisResponse.model_validate(res.json())
    assert body.planned_calls > 0
    assert body.estimated_new_calls == 0 and body.cached_calls == body.planned_calls
    assert body.can_run is True and body.blocked_reason is None
    assert body.needs_access_code is False and body.live_enabled is False
    assert body.as_of_date.isoformat() == "2026-08-10"


def test_estimate_still_validates_input(client):
    bad = {**ESTIMATE_BODY, "competitors": ["A", "B", "C"]}
    assert client.post(f"{P}/analyses/estimate", json=bad).status_code == 422


@pytest.mark.parametrize("alias", ["demo-signal-battery", DEMO_SIGNAL_ID, "demo"])
def test_signal_detail_and_investigate(client, alias):
    assert SignalDetail.model_validate(client.get(f"{P}/signals/{alias}").json())
    for path in (f"{P}/signals/{alias}/investigate", f"{P}/signals/{alias}/investigate?force=true"):
        res = client.post(path)
        assert res.status_code == 200, res.text  # reuse of the bundled report, never 202/404
        body = InvestigateSignalResponse.model_validate(res.json())
        assert body.reused is True and body.status.value == "completed"
        assert str(body.investigation_id) == DEMO_INVESTIGATION_ID
        assert body.poll_url == f"{P}/investigations/{DEMO_INVESTIGATION_ID}"


def test_investigate_poll_url_resolves(client):
    poll = client.post(f"{P}/signals/demo-signal-battery/investigate").json()["poll_url"]
    res = client.get(poll)
    assert res.status_code == 200
    assert InvestigationResponse.model_validate(res.json()).report is not None


@pytest.mark.parametrize("alias", ["demo", "demo-investigation", DEMO_INVESTIGATION_ID])
def test_investigation_and_evidence(client, alias):
    assert InvestigationResponse.model_validate(
        client.get(f"{P}/investigations/{alias}").json()
    )
    res = client.get(f"{P}/investigations/{alias}/evidence")
    assert res.status_code == 200
    for item in ListEvidenceResponse.model_validate(res.json()).items:
        assert isinstance(item, EvidenceItem)


def test_health_reports_demo_mode(client):
    assert client.get(f"{P}/health").json()["demo_mode"] is True


def test_demo_aliases_are_ordinary_ids_when_demo_mode_is_off(make_client):
    client = make_client()  # DEMO_MODE off, no database
    assert client.get(f"{P}/analyses/demo/mentions").status_code == 404
    assert client.post(f"{P}/signals/demo-signal-battery/investigate").status_code == 404
    assert client.get(f"{P}/usage").status_code == 501
    assert client.post(f"{P}/analyses/estimate", json=ESTIMATE_BODY).status_code == 501
