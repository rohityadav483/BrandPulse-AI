"""LLMService: one audit record per provider call, and the concurrency limit is honored."""

import threading
import time
import urllib.error
from types import SimpleNamespace

import pytest

from app.services.llm.base import LLMResult
from app.services.llm.limiter import LLMLimiter, shared_limiter
from app.services.llm.service import LLMService


class Recorder:
    def __init__(self):
        self.rows = []

    def record(self, **fields):
        self.rows.append(fields)


class Provider:
    model = "fake-model"

    def __init__(self, outcome):
        self.outcome = outcome

    def complete(self, prompt, *, system=None):
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


def _service(outcome, **kw):
    rec = Recorder()
    return LLMService(Provider(outcome), recorder=rec, **kw), rec


def test_successful_call_is_recorded_with_usage():
    svc, rec = _service(LLMResult('{"a": 1}', tokens_in=11, tokens_out=7, latency_ms=42))
    assert svc.complete_json("p") == {"a": 1}
    assert rec.rows == [
        {"model": "fake-model", "status": "ok", "tokens_in": 11, "tokens_out": 7, "latency_ms": 42}
    ]


def test_invalid_json_is_recorded_and_raised():
    svc, rec = _service(LLMResult("not json", tokens_in=3, tokens_out=2, latency_ms=5))
    with pytest.raises(ValueError):
        svc.complete_json("p")
    (row,) = rec.rows
    assert row["status"] == "invalid_json" and row["tokens_in"] == 3 and row["error"]


def test_non_object_json_is_recorded_as_invalid_json():
    svc, rec = _service(LLMResult("[1, 2]"))
    with pytest.raises(TypeError):
        svc.complete_json("p")
    assert rec.rows[0]["status"] == "invalid_json"


def test_http_429_is_rate_limited_and_other_errors_are_failed():
    limited = urllib.error.HTTPError("https://x", 429, "Too Many Requests", {}, None)
    svc, rec = _service(limited)
    with pytest.raises(urllib.error.HTTPError):
        svc.complete_json("p")
    assert rec.rows[0]["status"] == "rate_limited"

    svc, rec = _service(TimeoutError("timed out"))
    with pytest.raises(TimeoutError):
        svc.complete_json("p")
    assert rec.rows[0]["status"] == "failed" and "timed out" in rec.rows[0]["error"]


def test_call_budget_blocks_the_provider_and_records_nothing():
    svc, rec = _service(LLMResult("{}"), max_calls=1)
    svc.complete_json("p")
    with pytest.raises(RuntimeError, match="llm_unavailable"):
        svc.complete_json("p")
    assert len(rec.rows) == 1
    off = LLMService(None, recorder=rec)
    with pytest.raises(RuntimeError, match="llm_unavailable"):
        off.complete_json("p")
    assert len(rec.rows) == 1


def _hammer(limiter: LLMLimiter, threads: int) -> int:
    live = 0
    peak = 0
    lock = threading.Lock()

    class Slow:
        model = "m"

        def complete(self, prompt, *, system=None):
            nonlocal live, peak
            with lock:
                live += 1
                peak = max(peak, live)
            time.sleep(0.03)
            with lock:
                live -= 1
            return LLMResult("{}")

    def work():
        LLMService(Slow(), limiter=limiter).complete_json("p")

    pool = [threading.Thread(target=work) for _ in range(threads)]
    for t in pool:
        t.start()
    for t in pool:
        t.join()
    return peak


@pytest.mark.parametrize("limit", [1, 2, 3])
def test_limiter_caps_simultaneous_provider_calls(limit):
    limiter = LLMLimiter(max_concurrency=limit)
    assert _hammer(limiter, 8) == limit
    assert limiter.peak == limit and limiter.active == 0


def test_shared_limiter_follows_the_setting_on_every_call():
    assert shared_limiter(1).max_concurrency == 1
    assert shared_limiter(3).max_concurrency == 3
    assert shared_limiter(0).max_concurrency == 1  # never below one
    shared_limiter(1)


def test_slot_is_released_when_the_provider_raises():
    limiter = LLMLimiter(max_concurrency=1)
    svc = LLMService(Provider(RuntimeError("boom")), limiter=limiter)
    with pytest.raises(RuntimeError):
        svc.complete_json("p")
    assert limiter.active == 0
    # A second call is not blocked behind the failed one.
    svc.provider = Provider(LLMResult("{}"))
    assert svc.complete_json("p") == {}


def test_recorder_failure_never_breaks_the_call(monkeypatch):
    from app.services.llm.audit import LLMCallRecorder

    def broken_session(*_a, **_k):
        raise RuntimeError("db down")

    monkeypatch.setattr("app.services.llm.audit.Session", broken_session)
    rec = LLMCallRecorder(SimpleNamespace(), task="t", prompt_version="v")
    rec.record(model="m", status="ok")  # must not raise
