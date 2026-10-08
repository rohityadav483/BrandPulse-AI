from __future__ import annotations


def test_investigation_routes_return_501_without_database(make_client):
    client = make_client(demo_mode=False)
    response = client.get("/api/v1/investigations/00000000-0000-4000-8000-000000000030")
    assert response.status_code == 501
    assert response.json()["error"]["code"] == "not_implemented"


def test_investigation_evidence_returns_501_without_database(make_client):
    client = make_client(demo_mode=False)
    response = client.get("/api/v1/investigations/00000000-0000-4000-8000-000000000030/evidence")
    assert response.status_code == 501
    assert response.json()["error"]["code"] == "not_implemented"

