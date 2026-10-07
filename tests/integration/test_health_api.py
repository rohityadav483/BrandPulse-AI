import app.api.v1.health as health_module


def _db(monkeypatch, ok: bool):
    monkeypatch.setattr(health_module, "check_database", lambda url: ok)


def test_health_ok_when_database_reachable(make_client, monkeypatch):
    _db(monkeypatch, True)
    monkeypatch.setattr(health_module, "nlp_status", lambda *args: "ok")
    res = make_client(database_url="postgresql://x").get("/api/v1/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"
    assert body["version"] == "0.1.0"
    assert body["nlp"] == "ok"
    assert set(body) == {
        "status",
        "version",
        "database",
        "nlp",
        "serpapi_configured",
        "live_serpapi_enabled",
        "groq_configured",
        "demo_mode",
    }


def test_health_degraded_when_database_unreachable(make_client, monkeypatch):
    _db(monkeypatch, False)
    res = make_client().get("/api/v1/health")
    assert res.status_code == 200
    assert res.json()["status"] == "degraded"
    assert res.json()["database"] == "unavailable"


def test_health_degraded_without_database_url(make_client):
    body = make_client().get("/api/v1/health").json()
    assert body["status"] == "degraded" and body["database"] == "unavailable"


def test_health_reports_flags_and_never_leaks_keys(make_client, monkeypatch):
    _db(monkeypatch, True)
    client = make_client(
        serpapi_api_key="sk-secret-1",
        groq_api_key="gq-secret-2",
        live_access_code="code-3",
        database_url="postgresql://u:dbpass-4@h/db",
        allow_live_serpapi=True,
        demo_mode=True,
    )
    res = client.get("/api/v1/health")
    body = res.json()
    assert body["serpapi_configured"] is True
    assert body["groq_configured"] is True
    assert body["live_serpapi_enabled"] is True
    assert body["demo_mode"] is True
    for secret in ("sk-secret-1", "gq-secret-2", "code-3", "dbpass-4"):
        assert secret not in res.text


def test_health_flags_default_false(make_client, monkeypatch):
    _db(monkeypatch, True)
    body = make_client().get("/api/v1/health").json()
    assert body["serpapi_configured"] is False
    assert body["groq_configured"] is False
    assert body["live_serpapi_enabled"] is False
    assert body["demo_mode"] is False


def test_response_has_request_id_header(make_client, monkeypatch):
    _db(monkeypatch, True)
    client = make_client()
    assert client.get("/api/v1/health").headers["X-Request-ID"]
    echoed = client.get("/api/v1/health", headers={"X-Request-ID": "req-42"})
    assert echoed.headers["X-Request-ID"] == "req-42"


def test_openapi_operation_id_is_stable(make_client):
    spec = make_client().get("/openapi.json").json()
    assert spec["paths"]["/api/v1/health"]["get"]["operationId"] == "getHealth"


def test_health_degraded_when_nlp_unavailable(make_client, monkeypatch):
    _db(monkeypatch, True)
    monkeypatch.setattr(health_module, "nlp_status", lambda *args: "unavailable")
    body = make_client(database_url="postgresql://x").get("/api/v1/health").json()
    assert body["status"] == "degraded"
    assert body["nlp"] == "unavailable"
