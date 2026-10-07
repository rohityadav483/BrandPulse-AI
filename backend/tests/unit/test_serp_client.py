import pytest

from app.schemas.serp import QuerySpec, SerpEngine
from app.services.serpapi import client as client_module
from app.services.serpapi.client import (
    SerpApiAccountQuotaExhausted,
    SerpApiAuthError,
    SerpApiBadRequest,
    SerpApiClient,
    SerpApiLiveDisabled,
    SerpApiNotConfigured,
    SerpApiRateLimited,
    SerpApiResponseError,
    SerpApiServerError,
    SerpApiTimeout,
    TransportResponse,
)
from app.services.serpapi.testing import ScriptedTransport, block_network, ok

KEY = "SECRET-KEY-123"
SPEC = QuerySpec(engine=SerpEngine.google, params={"q": "samsung", "safe": True})
GOOD = {"organic_results": [{"title": "t", "link": "https://a.example.test"}]}


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    block_network(monkeypatch)


def make(script, *, allow_live=True, key=KEY, retries=2):
    transport = ScriptedTransport(script)
    sleeps: list[float] = []
    client = SerpApiClient(
        api_key=key,
        allow_live=allow_live,
        transport=transport,
        max_retries=retries,
        sleep=sleeps.append,
    )
    return client, transport, sleeps


def test_success_sends_engine_and_key_and_stringifies_params():
    client, transport, _ = make(lambda engine, params: ok(GOOD))
    result = client.fetch(SPEC)
    assert result.response == GOOD and result.http_status == 200 and result.attempts == 1
    assert transport.calls == [
        {"q": "samsung", "safe": "true", "engine": "google", "api_key": KEY}
    ]


def test_live_switch_off_never_reaches_transport():
    client, transport, _ = make(lambda e, p: ok(GOOD), allow_live=False)
    with pytest.raises(SerpApiLiveDisabled):
        client.fetch(SPEC)
    assert transport.calls == []


def test_missing_key_never_reaches_transport():
    client, transport, _ = make(lambda e, p: ok(GOOD), key="")
    with pytest.raises(SerpApiNotConfigured):
        client.fetch(SPEC)
    assert transport.calls == []


def test_default_transport_cannot_open_a_socket_in_tests():
    client = SerpApiClient(api_key=KEY, allow_live=True, max_retries=0)
    with pytest.raises(Exception) as err:  # network is blocked: surfaces as a mapped error
        client.fetch(SPEC)
    assert KEY not in str(err.value)


@pytest.mark.parametrize(
    ("status", "body", "expected"),
    [
        (401, {"error": "Invalid API key"}, SerpApiAuthError),
        (403, {"error": "Forbidden"}, SerpApiAuthError),
        (400, {"error": "Missing query `q` parameter"}, SerpApiBadRequest),
        (404, None, SerpApiBadRequest),
        (429, {"error": "Your account has run out of searches."}, SerpApiAccountQuotaExhausted),
        (200, {"error": "Something broke upstream"}, SerpApiResponseError),
        (200, None, SerpApiResponseError),
    ],
)
def test_non_retryable_errors_are_mapped_and_not_retried(status, body, expected):
    client, transport, sleeps = make(lambda e, p: TransportResponse(status, body))
    with pytest.raises(expected) as err:
        client.fetch(SPEC)
    assert len(transport.calls) == 1 and sleeps == []
    assert err.value.http_status == status and err.value.attempts == 1


def test_no_results_payload_is_a_valid_empty_result():
    body = {"error": "Google hasn't returned any results for this query."}
    client, _, _ = make(lambda e, p: ok(body))
    assert client.fetch(SPEC).response == body


def test_retries_5xx_then_succeeds_with_exponential_backoff():
    busy = TransportResponse(503, {"error": "busy"})
    outcomes = iter([busy, TransportResponse(500, None), ok(GOOD)])
    client, transport, sleeps = make(lambda e, p: next(outcomes))
    result = client.fetch(SPEC)
    assert result.attempts == 3 and len(transport.calls) == 3
    assert sleeps == [1.0, 2.0]


def test_gives_up_after_max_retries():
    client, transport, _ = make(lambda e, p: TransportResponse(500, None), retries=2)
    with pytest.raises(SerpApiServerError) as err:
        client.fetch(SPEC)
    assert len(transport.calls) == 3 and err.value.attempts == 3


def test_rate_limit_honours_retry_after_and_caps_it():
    outcomes = iter([TransportResponse(429, {"error": "slow down"}, 7.0), ok(GOOD)])
    client, _, sleeps = make(lambda e, p: next(outcomes))
    client.fetch(SPEC)
    assert sleeps == [7.0]
    outcomes = iter([TransportResponse(429, {"error": "slow down"}, 999.0), ok(GOOD)])
    client, _, sleeps = make(lambda e, p: next(outcomes))
    client.fetch(SPEC)
    assert sleeps == [30.0]


def test_rate_limit_error_type_after_retries():
    client, _, _ = make(lambda e, p: TransportResponse(429, {"error": "slow down"}), retries=1)
    with pytest.raises(SerpApiRateLimited):
        client.fetch(SPEC)


def test_timeouts_are_retried_then_raised():
    client, transport, _ = make(lambda e, p: SerpApiTimeout("timed out"), retries=1)
    with pytest.raises(SerpApiTimeout):
        client.fetch(SPEC)
    assert len(transport.calls) == 2


def test_key_never_leaks_in_errors_or_repr():
    body = {"error": f"bad request https://serpapi.com/search?api_key={KEY}&q=x"}
    client, _, _ = make(lambda e, p: TransportResponse(400, body))
    with pytest.raises(SerpApiBadRequest) as err:
        client.fetch(SPEC)
    assert KEY not in str(err.value) and KEY not in repr(client)


def test_urllib_transport_refuses_plain_http():
    with pytest.raises(SerpApiBadRequest):
        client_module.UrllibTransport().get("http://serpapi.com/search.json", {}, 1.0)
