import json

from fastapi import HTTPException
from pydantic import BaseModel

from app.api.v1.errors import ApiError


class Payload(BaseModel):
    name: str
    count: int


def _client(make_client):
    client = make_client()
    app = client.app

    @app.get("/t/api-error")
    def api_error():
        raise ApiError(
            409,
            "analysis_not_ready",
            "Analysis is still running.",
            {"status": "running", "stage": "analyzing"},
            headers={"Retry-After": "2"},
        )

    @app.get("/t/http-error")
    def http_error():
        raise HTTPException(status_code=403, detail="Nope.")

    @app.get("/t/query")
    def query(n: int):
        return {"n": n}

    @app.post("/t/body")
    def body(payload: Payload):
        return payload

    @app.get("/t/boom")
    def boom():
        raise RuntimeError("secret internal detail /srv/db-password")

    return client


def _assert_envelope(res, status, code):
    assert res.status_code == status
    body = res.json()
    assert set(body) == {"error"}
    assert set(body["error"]) == {"code", "message", "details"}
    assert body["error"]["code"] == code
    assert isinstance(body["error"]["details"], dict)
    return body["error"]


def test_api_error_uses_envelope_and_headers(make_client):
    res = _client(make_client).get("/t/api-error")
    err = _assert_envelope(res, 409, "analysis_not_ready")
    assert err["message"] == "Analysis is still running."
    assert err["details"] == {"status": "running", "stage": "analyzing"}
    assert res.headers["Retry-After"] == "2"


def test_unknown_route_is_not_found(make_client):
    err = _assert_envelope(_client(make_client).get("/nope"), 404, "not_found")
    assert err["details"] == {}


def test_wrong_method_is_405(make_client):
    res = _client(make_client).post("/api/v1/health")
    _assert_envelope(res, 405, "method_not_allowed")
    assert "GET" in res.headers["Allow"]


def test_http_exception_is_wrapped(make_client):
    err = _assert_envelope(
        _client(make_client).get("/t/http-error"), 403, "bad_request"
    )
    assert err["message"] == "Nope."


def test_query_validation_error(make_client):
    err = _assert_envelope(
        _client(make_client).get("/t/query?n=abc"), 422, "validation_error"
    )
    assert err["message"] == "Request validation failed."
    assert err["details"]["fields"][0]["field"] == "n"


def test_body_validation_error_lists_fields_and_hides_input(make_client):
    res = _client(make_client).post(
        "/t/body", json={"name": "x", "count": "TOP-SECRET-INPUT"}
    )
    err = _assert_envelope(res, 422, "validation_error")
    assert [f["field"] for f in err["details"]["fields"]] == ["count"]
    assert "TOP-SECRET-INPUT" not in res.text


def test_missing_body_field_is_reported(make_client):
    res = _client(make_client).post("/t/body", json={"name": "x"})
    err = _assert_envelope(res, 422, "validation_error")
    assert err["details"]["fields"][0]["field"] == "count"


def test_malformed_json_is_400(make_client):
    res = _client(make_client).post(
        "/t/body", content=b"{not json", headers={"Content-Type": "application/json"}
    )
    _assert_envelope(res, 400, "bad_request")


def test_unexpected_exception_is_500_and_never_leaks(make_client, capsys):
    res = _client(make_client).get("/t/boom")
    err = _assert_envelope(res, 500, "internal_error")
    assert err["message"] == "An unexpected error occurred."
    assert "db-password" not in res.text and "RuntimeError" not in res.text
    # Logged server-side as a JSON line with traceback and request id.
    lines = [
        json.loads(x) for x in capsys.readouterr().out.splitlines() if x.startswith("{")
    ]
    failed = [x for x in lines if x["message"] == "request_failed"]
    assert failed and "RuntimeError" in failed[0]["exception"]
    assert failed[0]["request_id"] and failed[0]["path"] == "/t/boom"
