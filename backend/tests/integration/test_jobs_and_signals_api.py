# ruff: noqa: F811, E501
"""Jobs, stale-job recovery and `POST /signals/{id}/investigate` against PostgreSQL.

Skipped without TEST_DATABASE_URL (uses the `migrated_engine` fixture). Covers:
  * concurrent analysis requests are queued, never dropped, never stuck `queued`;
  * the stale-job reaper runs on startup and before creating work;
  * the documented investigate contract: 404 / 403 / 409 / 429 / 501, reuse (200) vs
    create (202), `force`, failed investigations are not reused, single-flight under a race;
  * `Signal.status` transitions and `GET /signals/{id}` (`latest_investigation`, real role).
"""

import json
import threading
import uuid
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.api.v1 import analyses as analyses_api
from app.api.v1 import signals as signals_api
from app.main import create_app
from app.pipeline import investigation_pipeline, jobs
from app.pipeline.jobs import reap_stale_jobs, start_analysis_job

# Reuse the scripted-analysis fixtures (tests/ has no packages; rootdir imports are by basename).
from test_analysis_pipeline_e2e import (  # noqa: F401  (fixtures)
    RIVAL_A,
    TARGET,
    run_analysis,
    seeded,
    settings_for,
)

P = "/api/v1"
COMPONENTS = {"growth": 0.9, "frequency": 0.7, "cross_source": 0.6, "sentiment_impact": 0.8}
DONE = {"completed", "partial"}


# ----------------------------------------------------------------------------- helpers


def _sql(engine, sql, **params):
    with engine.begin() as conn:
        return conn.execute(text(sql), params)


def _one(engine, sql, **params):
    with engine.connect() as conn:
        return conn.execute(text(sql), params).one()


def _scalar(engine, sql, **params):
    with engine.connect() as conn:
        return conn.execute(text(sql), params).scalar_one()


def _insert_signal(engine, analysis_id, brand_id) -> uuid.UUID:
    return _scalar_returning(
        engine,
        "INSERT INTO signals (analysis_id, brand_id, kind, aspect, baseline_n, baseline_total, "
        "current_n, current_total, baseline_share, current_share, growth, components, "
        "signal_score, impact, signal_confidence, sources_count, source_types) VALUES "
        "(:a, :b, 'aspect_negative_spike', 'battery', 1, 8, 6, 8, 0.125, 0.75, 5.0, "
        "CAST(:c AS jsonb), 0.82, 'high', 78, 3, ARRAY['news','web','forum']) RETURNING id",
        a=analysis_id,
        b=brand_id,
        c=json.dumps(COMPONENTS),
    )


def _scalar_returning(engine, sql, **params):
    with engine.begin() as conn:
        return conn.execute(text(sql), params).scalar_one()


def _investigations(engine, signal_id):
    with engine.connect() as conn:
        return conn.execute(
            text(
                "SELECT id, status, step FROM investigations WHERE signal_id = :s "
                "ORDER BY created_at, id"
            ),
            {"s": signal_id},
        ).all()


def _signal_status(engine, signal_id) -> str:
    return _scalar(engine, "SELECT status::text FROM signals WHERE id = :s", s=signal_id)


def _insert_analysis(engine, ids, *, status="queued", started_ago=None, created_ago=None):
    """A Samsung analysis with Apple + OnePlus, same windows as the `seeded` fixture."""
    created = f"now() - interval '{created_ago}'" if created_ago else "now()"
    started = f"now() - interval '{started_ago}'" if started_ago else "NULL"
    aid = _scalar_returning(
        engine,
        "INSERT INTO analyses (brand_id, product, as_of_date, current_start, current_end, "
        "baseline_start, baseline_end, status, created_at, started_at) VALUES (:b, "
        "'Galaxy S25 Ultra', :a, :cs, :ce, :bs, :be, :st, "
        f"{created}, {started}) RETURNING id",
        b=ids[TARGET],
        a=date(2026, 8, 10),
        cs=date(2026, 7, 12),
        ce=date(2026, 8, 10),
        bs=date(2026, 6, 12),
        be=date(2026, 7, 11),
        st=status,
    )
    for name, role in ((TARGET, "target"), (RIVAL_A, "competitor"), ("OnePlus", "competitor")):
        _sql(
            engine,
            "INSERT INTO analysis_brands (analysis_id, brand_id, role) VALUES (:a, :b, :r)",
            a=aid,
            b=ids[name],
            r=role,
        )
    return aid


@pytest.fixture(autouse=True)
def _reset_state(monkeypatch):
    analyses_api._RATE.clear()
    jobs._gate = jobs._Gate()
    jobs._investigation_gate = jobs._Gate()
    yield
    analyses_api._RATE.clear()


@pytest.fixture
def started(monkeypatch):
    """Replace the investigation job with a recorder, so only the API contract is exercised."""
    calls = []
    monkeypatch.setattr(signals_api, "start_investigation_job", lambda iid, s: calls.append(iid))
    return calls


@pytest.fixture
def world(migrated_engine, seeded):
    """A finished analysis with a target signal (Samsung) and a competitor signal (Apple)."""
    analysis_id, ids = seeded
    _sql(migrated_engine, "UPDATE analyses SET status = 'completed' WHERE id = :a", a=analysis_id)
    return {
        "analysis_id": analysis_id,
        "ids": ids,
        "target_signal": _insert_signal(migrated_engine, analysis_id, ids[TARGET]),
        "competitor_signal": _insert_signal(migrated_engine, analysis_id, ids[RIVAL_A]),
    }


@pytest.fixture
def client(settings_for, make_client):
    """Live SerpApi disabled: an investigation needs no access code or quota."""
    return make_client(database_url=settings_for.database_url)


@pytest.fixture
def live_client(settings_for, make_client):
    def _make(**overrides):
        return make_client(
            database_url=settings_for.database_url,
            serpapi_api_key="test-key",
            allow_live_serpapi=True,
            **overrides,
        )

    return _make


def _investigate(client, signal_id, **params):
    qs = "".join(f"&{k}={v}" for k, v in params.items()).replace("&", "?", 1)
    return client.post(f"{P}/signals/{signal_id}/investigate{qs}")


# ----------------------------------------------------------------- 1. concurrent analyses


def test_concurrent_analysis_jobs_all_finish_and_never_overlap(
    migrated_engine, settings_for, seeded, monkeypatch
):
    _, ids = seeded
    real = jobs.run_analysis
    lock, state = threading.Lock(), {"active": 0, "peak": 0}

    def spy(analysis_id, settings):
        with lock:
            state["active"] += 1
            state["peak"] = max(state["peak"], state["active"])
        try:
            real(analysis_id, settings)
        finally:
            with lock:
                state["active"] -= 1

    monkeypatch.setattr(jobs, "run_analysis", spy)
    assert settings_for.max_concurrent_analyses == 1
    aids = [_insert_analysis(migrated_engine, ids) for _ in range(3)]
    threads = [
        threading.Thread(target=start_analysis_job, args=(a, settings_for)) for a in aids
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(120)
        assert not t.is_alive()

    with migrated_engine.connect() as conn:
        rows = conn.execute(
            text("SELECT status::text, error FROM analyses WHERE id = ANY(:ids)"), {"ids": aids}
        ).all()
    assert [r[0] for r in rows] and all(r[0] in DONE for r in rows), rows  # none left queued
    assert state["peak"] == 1


def test_back_to_back_analysis_requests_both_run(
    migrated_engine, settings_for, seeded, live_client, monkeypatch
):
    monkeypatch.setattr(analyses_api, "nlp_status", lambda *a, **k: "ok")
    client = live_client(max_analyses_per_day=10)
    body = {
        "brand": TARGET,
        "product": "Galaxy S25 Ultra",
        "competitors": [RIVAL_A, "OnePlus"],
        "as_of_date": "2026-08-10",
    }
    first = client.post(f"{P}/analyses", json=body)
    second = client.post(f"{P}/analyses", json=body)
    assert first.status_code == 202 and second.status_code == 202, (first.text, second.text)
    for res in (first, second):
        status = client.get(res.json()["poll_url"]).json()["status"]
        assert status in DONE, status  # the second request was not silently dropped


def test_job_that_cannot_get_a_slot_is_failed_with_a_reason(
    migrated_engine, settings_for, seeded, monkeypatch
):
    _, ids = seeded
    aid = _insert_analysis(migrated_engine, ids)
    assert jobs._gate.acquire(1, 1)  # another analysis holds the only slot
    try:
        start_analysis_job(aid, settings_for, queue_wait_seconds=0.1)
    finally:
        jobs._gate.release()
    row = _one(migrated_engine, "SELECT status::text, error FROM analyses WHERE id = :a", a=aid)
    assert row[0] == "failed" and "busy" in row[1]


def test_escaped_pipeline_crash_marks_the_row_failed(
    migrated_engine, settings_for, seeded, monkeypatch
):
    _, ids = seeded
    aid = _insert_analysis(migrated_engine, ids)

    def boom(analysis_id, settings):
        raise RuntimeError("boom")

    monkeypatch.setattr(jobs, "run_analysis", boom)
    start_analysis_job(aid, settings_for)
    assert _scalar(migrated_engine, "SELECT status::text FROM analyses WHERE id = :a", a=aid) == "failed"
    assert jobs._gate.running == 0


# --------------------------------------------------------------------- 2. stale-job reaper


def test_reaper_recovers_stale_rows_and_leaves_fresh_ones(migrated_engine, settings_for, seeded):
    _, ids = seeded
    stale_running = _insert_analysis(migrated_engine, ids, status="running", started_ago="3 hours")
    stale_queued = _insert_analysis(migrated_engine, ids, status="queued", created_ago="3 hours")
    fresh_running = _insert_analysis(migrated_engine, ids, status="running", started_ago="1 minute")
    fresh_queued = _insert_analysis(migrated_engine, ids, status="queued")

    assert reap_stale_jobs(settings_for) == 2

    def row(a):
        return _one(
            migrated_engine,
            "SELECT status::text, error, finished_at IS NOT NULL FROM analyses WHERE id = :a",
            a=a,
        )

    assert row(stale_running)[0] == "partial" and "stale" in row(stale_running)[1]
    assert row(stale_running)[2] is True
    assert row(stale_queued)[0] == "failed" and row(stale_queued)[2] is True
    assert row(fresh_running)[0] == "running"
    assert row(fresh_queued)[0] == "queued"
    assert reap_stale_jobs(settings_for) == 0  # idempotent


def test_app_startup_runs_the_reaper(migrated_engine, settings_for, seeded, make_settings):
    _, ids = seeded
    stale = _insert_analysis(migrated_engine, ids, status="running", started_ago="2 hours")
    with TestClient(create_app(make_settings(database_url=settings_for.database_url))):
        pass  # entering the context runs the lifespan startup
    assert _scalar(migrated_engine, "SELECT status::text FROM analyses WHERE id = :a", a=stale) == "partial"


def test_startup_without_a_database_does_not_fail(make_settings):
    with TestClient(create_app(make_settings())) as client:
        assert client.get(f"{P}/health").status_code == 200


def test_creating_an_analysis_reaps_stale_rows(
    migrated_engine, settings_for, seeded, live_client, monkeypatch
):
    _, ids = seeded
    stale = _insert_analysis(migrated_engine, ids, status="running", started_ago="2 hours")
    monkeypatch.setattr(analyses_api, "nlp_status", lambda *a, **k: "ok")
    monkeypatch.setattr(analyses_api, "start_analysis_job", lambda *a, **k: None)
    res = live_client(max_analyses_per_day=10).post(
        f"{P}/analyses",
        json={"brand": TARGET, "competitors": [RIVAL_A], "as_of_date": "2026-08-10"},
    )
    assert res.status_code == 202, res.text
    assert _scalar(migrated_engine, "SELECT status::text FROM analyses WHERE id = :a", a=stale) == "partial"


def test_reaper_fails_stale_investigations_and_resets_the_signal(
    migrated_engine, settings_for, world, client, started
):
    sid = world["target_signal"]
    _sql(
        migrated_engine,
        "INSERT INTO investigations (signal_id, analysis_id, status, created_at) "
        "VALUES (:s, :a, 'running', now() - interval '3 hours')",
        s=sid,
        a=world["analysis_id"],
    )
    _sql(migrated_engine, "UPDATE signals SET status = 'investigating' WHERE id = :s", s=sid)

    assert reap_stale_jobs(settings_for) == 1
    assert [r[1] for r in _investigations(migrated_engine, sid)] == ["failed"]
    assert _signal_status(migrated_engine, sid) == "detected"
    assert _investigate(client, sid).status_code == 202  # no longer blocked by the dead row


# ------------------------------------------------------------ 3. investigate: error contract


def test_unknown_and_malformed_ids_return_404(client, started):
    assert _investigate(client, uuid.uuid4()).status_code == 404
    res = _investigate(client, "not-a-uuid")
    assert res.status_code == 404 and res.json()["error"]["code"] == "not_found"
    assert started == []


def test_no_database_returns_501(make_client):
    res = make_client().post(f"{P}/signals/{uuid.uuid4()}/investigate")
    assert res.status_code == 501
    assert make_client().get(f"{P}/signals/{uuid.uuid4()}").status_code == 501


@pytest.mark.parametrize("analysis_status", ["queued", "running", "failed"])
def test_signal_of_an_unfinished_analysis_is_not_investigable(
    migrated_engine, world, client, started, analysis_status
):
    _sql(
        migrated_engine,
        "UPDATE analyses SET status = :s WHERE id = :a",
        s=analysis_status,
        a=world["analysis_id"],
    )
    res = _investigate(client, world["target_signal"])
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "signal_not_investigable"
    assert _investigations(migrated_engine, world["target_signal"]) == []
    assert _signal_status(migrated_engine, world["target_signal"]) == "detected"
    assert started == []


def test_partial_analysis_is_investigable(migrated_engine, world, client, started):
    _sql(migrated_engine, "UPDATE analyses SET status = 'partial' WHERE id = :a", a=world["analysis_id"])
    assert _investigate(client, world["target_signal"]).status_code == 202


def test_rate_limit_returns_429(client, world, started, monkeypatch):
    monkeypatch.setattr(signals_api, "_rate_ok", lambda key: False)
    res = _investigate(client, world["target_signal"])
    assert res.status_code == 429 and res.json()["error"]["code"] == "rate_limited"
    assert started == []


# -------------------------------------------------------------------- access code / quota


def test_access_code_is_enforced_for_new_live_investigations(
    migrated_engine, world, live_client, started
):
    client = live_client(live_access_code="s3cret")
    sid = world["target_signal"]
    for headers in ({}, {"X-Access-Code": "wrong"}):
        res = client.post(f"{P}/signals/{sid}/investigate", headers=headers)
        assert res.status_code == 403, res.text
        assert res.json()["error"]["code"] == "live_access_required"
    assert _investigations(migrated_engine, sid) == [] and started == []

    ok = client.post(f"{P}/signals/{sid}/investigate", headers={"X-Access-Code": "s3cret"})
    assert ok.status_code == 202 and len(started) == 1

    # Reusing an existing investigation costs nothing, so it needs no code.
    again = client.post(f"{P}/signals/{sid}/investigate")
    assert again.status_code == 200 and again.json()["reused"] is True


def test_access_code_not_needed_when_live_calls_are_disabled(world, make_client, settings_for, started):
    client = make_client(database_url=settings_for.database_url, live_access_code="s3cret")
    assert client.post(f"{P}/signals/{world['target_signal']}/investigate").status_code == 202


def test_low_serpapi_quota_returns_429(migrated_engine, world, live_client, started):
    client = live_client(serp_monthly_limit=5, serp_monthly_reserve=2)  # budget 8 > 5 - 2
    res = client.post(f"{P}/signals/{world['target_signal']}/investigate")
    assert res.status_code == 429 and res.json()["error"]["code"] == "serpapi_quota_low"
    assert _investigations(migrated_engine, world["target_signal"]) == []


# ---------------------------------------------------- reuse / force / single-flight / status


def test_create_then_reuse_while_active_and_status_transitions(migrated_engine, world, client, started):
    sid = world["target_signal"]
    assert _signal_status(migrated_engine, sid) == "detected"

    created = _investigate(client, sid)
    assert created.status_code == 202
    body = created.json()
    assert body["reused"] is False and body["status"] == "queued"
    assert body["poll_url"] == f"{P}/investigations/{body['investigation_id']}"
    assert started == [uuid.UUID(body["investigation_id"])]
    assert _signal_status(migrated_engine, sid) == "investigating"

    again = _investigate(client, sid)  # double-click while queued
    assert again.status_code == 200
    assert again.json()["investigation_id"] == body["investigation_id"]
    assert again.json()["reused"] is True
    assert len(started) == 1 and len(_investigations(migrated_engine, sid)) == 1


def test_force_while_active_is_rejected(migrated_engine, world, client, started):
    sid = world["target_signal"]
    assert _investigate(client, sid).status_code == 202
    for state in ("queued", "running"):
        _sql(migrated_engine, "UPDATE investigations SET status = :s WHERE signal_id = :g", s=state, g=sid)
        res = _investigate(client, sid, force="true")
        assert res.status_code == 409
        assert res.json()["error"]["code"] == "investigation_in_progress"
    assert len(_investigations(migrated_engine, sid)) == 1 and len(started) == 1


def test_running_investigation_is_reused(migrated_engine, world, client, started):
    sid = world["target_signal"]
    first = _investigate(client, sid).json()
    _sql(migrated_engine, "UPDATE investigations SET status = 'running' WHERE signal_id = :g", g=sid)
    res = _investigate(client, sid)
    assert res.status_code == 200 and res.json()["status"] == "running"
    assert res.json()["investigation_id"] == first["investigation_id"]


def test_completed_is_reused_unless_forced(migrated_engine, world, client, started):
    sid = world["target_signal"]
    first = _investigate(client, sid).json()
    _sql(migrated_engine, "UPDATE investigations SET status = 'completed' WHERE signal_id = :g", g=sid)

    reused = _investigate(client, sid)
    assert reused.status_code == 200 and reused.json()["reused"] is True
    assert reused.json()["status"] == "completed"
    assert reused.json()["investigation_id"] == first["investigation_id"]

    forced = _investigate(client, sid, force="true")
    assert forced.status_code == 202 and forced.json()["reused"] is False
    assert forced.json()["investigation_id"] != first["investigation_id"]
    assert len(_investigations(migrated_engine, sid)) == 2 and len(started) == 2
    assert _signal_status(migrated_engine, sid) == "investigating"


def test_failed_investigation_is_not_reused(migrated_engine, world, client, started):
    sid = world["target_signal"]
    first = _investigate(client, sid).json()
    _sql(migrated_engine, "UPDATE investigations SET status = 'failed' WHERE signal_id = :g", g=sid)
    res = _investigate(client, sid)  # no force needed
    assert res.status_code == 202 and res.json()["reused"] is False
    assert res.json()["investigation_id"] != first["investigation_id"]


def test_older_completed_is_reused_over_a_newer_failed(migrated_engine, world, client, started):
    sid = world["target_signal"]
    aid = world["analysis_id"]
    done = _scalar_returning(
        migrated_engine,
        "INSERT INTO investigations (signal_id, analysis_id, status, created_at) VALUES "
        "(:s, :a, 'completed', now() - interval '2 minutes') RETURNING id",
        s=sid,
        a=aid,
    )
    _sql(
        migrated_engine,
        "INSERT INTO investigations (signal_id, analysis_id, status) VALUES (:s, :a, 'failed')",
        s=sid,
        a=aid,
    )
    res = _investigate(client, sid)
    assert res.status_code == 200 and res.json()["investigation_id"] == str(done)


def test_concurrent_double_click_creates_exactly_one_investigation(
    migrated_engine, world, settings_for, make_client, started
):
    sid = world["target_signal"]
    clients = [make_client(database_url=settings_for.database_url) for _ in range(4)]
    barrier = threading.Barrier(len(clients))
    results = []

    def click(c):
        barrier.wait(5)
        results.append(_investigate(c, sid))

    threads = [threading.Thread(target=click, args=(c,)) for c in clients]
    for t in threads:
        t.start()
    for t in threads:
        t.join(30)

    assert sorted(r.status_code for r in results) == [200, 200, 200, 202]
    assert len({r.json()["investigation_id"] for r in results}) == 1
    assert len(_investigations(migrated_engine, sid)) == 1
    assert len(started) == 1


# ------------------------------------------------------------ GET /signals/{id}


def test_get_signal_latest_investigation_and_roles(migrated_engine, world, client, started):
    sid, csid = world["target_signal"], world["competitor_signal"]

    target = client.get(f"{P}/signals/{sid}").json()
    assert target["latest_investigation"] is None and target["status"] == "detected"
    assert target["brand"]["role"] == "target" and target["brand"]["name"] == TARGET
    competitor = client.get(f"{P}/signals/{csid}").json()
    assert competitor["brand"]["role"] == "competitor" and competitor["brand"]["name"] == RIVAL_A

    first = _investigate(client, sid).json()["investigation_id"]
    detail = client.get(f"{P}/signals/{sid}").json()
    assert detail["latest_investigation"] == {"id": first, "status": "queued"}
    assert detail["status"] == "investigating"

    _sql(migrated_engine, "UPDATE investigations SET status = 'completed' WHERE signal_id = :g", g=sid)
    second = _investigate(client, sid, force="true").json()["investigation_id"]
    latest = client.get(f"{P}/signals/{sid}").json()["latest_investigation"]
    assert latest == {"id": second, "status": "queued"}  # newest wins
    # The competitor signal is untouched by the target's investigations.
    assert client.get(f"{P}/signals/{csid}").json()["latest_investigation"] is None


def test_competitor_signals_are_investigable(migrated_engine, world, client, started):
    res = _investigate(client, world["competitor_signal"])
    assert res.status_code == 202
    assert _signal_status(migrated_engine, world["competitor_signal"]) == "investigating"
    assert _signal_status(migrated_engine, world["target_signal"]) == "detected"


# ------------------------------------------- real pipeline: status + latest_investigation


def test_real_investigation_updates_signal_status_end_to_end(
    migrated_engine, settings_for, world, live_client
):
    run_analysis(world["analysis_id"], settings_for)  # real content for the evidence step
    _sql(migrated_engine, "UPDATE analyses SET status = 'completed' WHERE id = :a", a=world["analysis_id"])
    client = live_client()
    sid = world["target_signal"]

    created = _investigate(client, sid)  # TestClient runs the background job before returning
    assert created.status_code == 202, created.text
    iid = created.json()["investigation_id"]
    inv = client.get(f"{P}/investigations/{iid}").json()
    assert inv["status"] == "completed", inv
    assert inv["report"] is not None and {s["state"] for s in inv["steps"]} == {"done"}

    assert _signal_status(migrated_engine, sid) == "investigated"
    detail = client.get(f"{P}/signals/{sid}").json()
    assert detail["status"] == "investigated"
    assert detail["latest_investigation"] == {"id": iid, "status": "completed"}

    reused = _investigate(client, sid)
    assert reused.status_code == 200 and reused.json()["investigation_id"] == iid

    forced = _investigate(client, sid, force="true")
    assert forced.status_code == 202 and forced.json()["investigation_id"] != iid
    assert client.get(f"{P}/signals/{sid}").json()["latest_investigation"]["id"] == forced.json()["investigation_id"]
    assert _signal_status(migrated_engine, sid) == "investigated"


def test_failed_investigation_returns_signal_to_detected_and_can_be_retried(
    migrated_engine, settings_for, world, live_client, monkeypatch
):
    run_analysis(world["analysis_id"], settings_for)
    _sql(migrated_engine, "UPDATE analyses SET status = 'completed' WHERE id = :a", a=world["analysis_id"])
    client = live_client()
    sid = world["target_signal"]

    def boom(*args, **kwargs):
        raise RuntimeError("query generation exploded")

    real_generate_queries = investigation_pipeline.generate_queries
    monkeypatch.setattr(investigation_pipeline, "generate_queries", boom)
    first = _investigate(client, sid)
    assert first.status_code == 202
    assert client.get(first.json()["poll_url"]).json()["status"] == "failed"
    assert _signal_status(migrated_engine, sid) == "detected"
    assert client.get(f"{P}/signals/{sid}").json()["latest_investigation"]["status"] == "failed"

    monkeypatch.setattr(investigation_pipeline, "generate_queries", real_generate_queries)
    retry = _investigate(client, sid)
    assert retry.status_code == 202 and retry.json()["investigation_id"] != first.json()["investigation_id"]
