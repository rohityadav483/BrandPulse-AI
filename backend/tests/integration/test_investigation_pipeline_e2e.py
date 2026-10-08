# ruff: noqa: F811
"""End-to-end `run_investigation` against PostgreSQL (skipped without TEST_DATABASE_URL).

Flow under test: signal -> evidence -> competitor comparison -> synthesis -> recommendations
-> stored report, polled through `GET /investigations/{id}` at every step.

Covers: detached ORM instances, step-state mismatch, `.priority.value` on a str, UUIDs in the
JSONB report, evidence-grounded synthesis and traceback logging. Content comes from a real
`run_analysis` (scripted SerpApi, stub sentiment model); the signal row is inserted directly
because the scripted data does not cross the spike threshold.
"""

import json
import logging
import re
import uuid
from datetime import UTC, datetime, time

import pytest
from pydantic import SecretStr
from sqlalchemy import text

# Reuse the scripted-analysis fixtures (tests/ has no packages; rootdir imports are by basename).
from test_analysis_pipeline_e2e import (  # noqa: F401  (fixtures)
    BRANDS,
    TARGET,
    run_analysis,
    seeded,
    settings_for,
)

from app.pipeline import investigation_pipeline
from app.pipeline.investigation_pipeline import run_investigation
from app.schemas.domain import StepState
from app.services.llm.base import LLMResult

VALID_STATES = {s.value for s in StepState}
ALL_STEPS = [
    "generating_queries",
    "collecting_evidence",
    "scoring_evidence",
    "comparing_competitors",
    "synthesizing",
    "recommending",
    "done",
]


@pytest.fixture
def investigation(migrated_engine, settings_for, seeded):  # noqa: F811
    """A completed analysis, a Samsung battery signal and a queued investigation."""
    analysis_id, ids = seeded
    run_analysis(analysis_id, settings_for)
    with migrated_engine.begin() as conn:
        signal_id = conn.execute(
            text(
                "INSERT INTO signals (analysis_id, brand_id, kind, aspect, baseline_n, "
                "baseline_total, current_n, current_total, baseline_share, current_share, "
                "growth, components, signal_score, impact, signal_confidence, sources_count, "
                "source_types) VALUES (:a, :b, 'aspect_negative_spike', 'battery', 1, 8, 6, 8, "
                "0.125, 0.75, 5.0, CAST(:c AS jsonb), 0.82, 'high', 78, 3, "
                "ARRAY['news','web','forums']) RETURNING id"
            ),
            {
                "a": analysis_id,
                "b": ids[TARGET],
                "c": json.dumps({"growth": 0.9, "volume": 0.7, "sources": 0.6, "recency": 0.8}),
            },
        ).scalar_one()
        investigation_id = conn.execute(
            text(
                "INSERT INTO investigations (signal_id, analysis_id) VALUES (:s, :a) RETURNING id"
            ),
            {"s": signal_id, "a": analysis_id},
        ).scalar_one()
    return investigation_id, signal_id, analysis_id, ids


@pytest.fixture
def client(settings_for, make_client):  # noqa: F811
    return make_client(
        database_url=settings_for.database_url,
        serpapi_api_key="test-key",
        allow_live_serpapi=True,
    )


def _row(engine, iid):
    with engine.connect() as conn:
        return conn.execute(
            text("SELECT status, step, steps, report, error FROM investigations WHERE id = :i"),
            {"i": iid},
        ).one()


def _evidence_ids(engine, iid):
    with engine.connect() as conn:
        return [
            str(r[0])
            for r in conn.execute(
                text("SELECT id FROM evidence WHERE investigation_id = :i ORDER BY rank"),
                {"i": iid},
            )
        ]


def _poll_at_every_step(monkeypatch, client, iid):
    """GET the investigation after every step transition (inside the pipeline thread)."""
    seen = []
    real = investigation_pipeline._set_step

    def spy(engine, investigation_id, step):
        real(engine, investigation_id, step)
        res = client.get(f"/api/v1/investigations/{iid}")
        seen.append((step, res.status_code, res.json() if res.status_code == 200 else res.text))

    real_queries = investigation_pipeline.generate_queries

    def queries_spy(*args, **kwargs):
        # First step is written together with status=running, before `_set_step` is used.
        res = client.get(f"/api/v1/investigations/{iid}")
        seen.append(("generating_queries", res.status_code, res.json()))
        return real_queries(*args, **kwargs)

    monkeypatch.setattr(investigation_pipeline, "_set_step", spy)
    monkeypatch.setattr(investigation_pipeline, "generate_queries", queries_spy)
    return seen


class RecordingGroq:
    """Stands in for GroqProvider: cites real, invented and missing evidence IDs."""

    model = "fake"
    prompts: list[str] = []

    def __init__(self, *_args, **_kwargs):
        pass

    def complete(self, prompt, *, system=None):
        RecordingGroq.prompts.append(prompt)
        ids = re.findall(r'"id": "([0-9a-f-]{36})"', prompt)
        assert ids, "prompt carried no evidence IDs"
        return LLMResult(
            text=json.dumps(
                {
                    "summary": "Battery complaints are associated with the spike.",
                    "findings": [
                        {"text": "Owners report fast drain.", "evidence_ids": [ids[0], ids[1]]},
                        {"text": "Invented source.", "evidence_ids": [str(uuid.uuid4())]},
                        {"text": "No citation at all.", "evidence_ids": []},
                        {"text": "Half real.", "evidence_ids": [ids[0], str(uuid.uuid4())]},
                    ],
                    "scope": {
                        "verdict": "brand_specific",
                        "ratio": 9,
                        "explanation": "LLM scope (overwritten by deterministic scope).",
                    },
                    "recommendations": [
                        {"title": "t", "action": "a", "rationale": "r", "evidence_ids": []},
                    ],
                }
            )
        )


def test_full_investigation_completes_and_get_is_200_throughout(
    migrated_engine, settings_for, investigation, client, monkeypatch
):
    iid, signal_id, analysis_id, ids = investigation

    queued = client.get(f"/api/v1/investigations/{iid}")
    assert queued.status_code == 200, queued.text
    assert queued.json()["status"] == "queued"
    assert queued.json()["report"] is None

    seen = _poll_at_every_step(monkeypatch, client, iid)
    run_investigation(iid, settings_for)

    # GET returned 200 with only API-valid states after every step transition.
    assert [s[0] for s in seen] == ALL_STEPS[:-1]  # `done` is written with the report
    for step, code, body in seen:
        assert code == 200, (step, body)
        assert body["status"] == "running" and body["step"] == step
        assert {x["state"] for x in body["steps"]} <= VALID_STATES
        states = {x["key"]: x["state"] for x in body["steps"]}
        assert states[step] == "active"
        assert body["report"] is None

    row = _row(migrated_engine, iid)
    assert row.error is None, row.error
    assert row.status == "completed" and row.step == "done"
    assert {x["state"] for x in row.steps} == {"done"}  # nothing left active/pending

    final = client.get(f"/api/v1/investigations/{iid}")
    assert final.status_code == 200, final.text
    body = final.json()
    assert body["status"] == "completed" and body["step"] == "done"
    assert [x["key"] for x in body["steps"]] == ALL_STEPS
    assert {x["state"] for x in body["steps"]} == {"done"}

    # Report is stored (JSONB) and retrievable, validated by the API response model.
    report = body["report"]
    assert report is not None
    assert report["generated_by"] == "fallback"  # no Groq key configured
    assert report["summary"]
    assert report["confidence"]["label"] in {"low", "medium", "high"}
    assert report["scope"]["verdict"] in {"brand_specific", "industry_wide", "inconclusive"}
    assert report["scope"]["ratio"] is not None  # two competitors were compared
    stored = row.report
    assert isinstance(stored["recommendations"][0]["id"], str)  # UUID -> str, not an object
    assert stored["recommendations"][0]["priority"] in {"high", "medium", "low"}

    # Evidence: persisted from the target brand's stored content, served by the API.
    evidence = _evidence_ids(migrated_engine, iid)
    assert evidence
    listed = client.get(f"/api/v1/investigations/{iid}/evidence")
    assert listed.status_code == 200, listed.text
    assert {i["id"] for i in listed.json()["items"]} == set(evidence[: len(listed.json()["items"])])

    # Every finding and recommendation cites only stored evidence.
    assert report["findings"]
    for f in report["findings"]:
        assert f["evidence_ids"] and set(f["evidence_ids"]) <= set(evidence)

    # Recommendations: rows in the table equal those embedded in the report.
    assert report["recommendations"]
    with migrated_engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT id, priority, evidence_ids FROM recommendations WHERE investigation_id = :i"
            ),
            {"i": iid},
        ).all()
    assert {str(r.id) for r in rows} == {r["id"] for r in report["recommendations"]}
    for r in report["recommendations"]:
        assert r["evidence_ids"] and set(r["evidence_ids"]) <= set(evidence)

    # Competitor comparison rows carry brand refs as plain JSON.
    comparison = report["competitor_comparison"]
    assert comparison["aspect"] == "battery"
    assert {row["brand"]["name"] for row in comparison["rows"]} == set(BRANDS)
    assert {row["brand"]["role"] for row in comparison["rows"]} == {"target", "competitor"}


def test_llm_report_keeps_valid_evidence_ids_and_drops_invalid_or_uncited(
    migrated_engine, settings_for, investigation, client, monkeypatch
):
    iid, *_ = investigation
    RecordingGroq.prompts = []
    monkeypatch.setattr(investigation_pipeline, "GroqProvider", RecordingGroq)
    settings = settings_for.model_copy(update={"groq_api_key": SecretStr("test-groq-key")})
    assert settings.groq_configured

    run_investigation(iid, settings)

    assert _row(migrated_engine, iid).error is None
    evidence = _evidence_ids(migrated_engine, iid)
    # The prompt really carried the stored evidence IDs.
    assert len(RecordingGroq.prompts) == 1
    for eid in evidence:
        assert eid in RecordingGroq.prompts[0]

    res = client.get(f"/api/v1/investigations/{iid}")
    assert res.status_code == 200, res.text
    report = res.json()["report"]
    assert report["generated_by"] == "llm"
    findings = report["findings"]
    assert [f["text"] for f in findings] == ["Owners report fast drain."]
    assert findings[0]["evidence_ids"] == evidence[:2]  # valid IDs preserved, in order
    # Deterministic scope and recommendations replace the model's (which cited nothing).
    assert report["scope"]["explanation"] != "LLM scope (overwritten by deterministic scope)."
    assert report["recommendations"]
    assert all(set(r["evidence_ids"]) <= set(evidence) for r in report["recommendations"])


def test_failure_logs_traceback_and_marks_failed_with_get_200(
    migrated_engine, settings_for, investigation, client, monkeypatch, caplog
):
    iid, *_ = investigation

    def boom(*_a, **_k):
        raise RuntimeError("collector exploded")

    monkeypatch.setattr(investigation_pipeline, "collect_existing", boom)
    with caplog.at_level(logging.ERROR, logger=investigation_pipeline.__name__):
        run_investigation(iid, settings_for)

    records = [r for r in caplog.records if r.exc_info and str(iid) in r.getMessage()]
    assert records, "no logger.exception record with the investigation id"
    assert records[0].exc_info[0] is RuntimeError
    assert "collector exploded" in caplog.text

    row = _row(migrated_engine, iid)
    assert row.status == "failed"
    assert row.error == "Investigation failed. Please try again."  # user-safe, no internals
    res = client.get(f"/api/v1/investigations/{iid}")
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "failed" and res.json()["report"] is None
    assert {x["state"] for x in res.json()["steps"]} <= VALID_STATES


def test_investigation_with_no_evidence_still_completes(
    migrated_engine, settings_for, investigation, client
):
    """Empty evidence: inconclusive fallback report, no recommendations, no crash."""
    iid, signal_id, analysis_id, ids = investigation
    with migrated_engine.begin() as conn:
        conn.execute(text("DELETE FROM content_items WHERE brand_id = :b"), {"b": ids[TARGET]})
    run_investigation(iid, settings_for)
    row = _row(migrated_engine, iid)
    assert row.error is None and row.status == "completed"
    res = client.get(f"/api/v1/investigations/{iid}")
    assert res.status_code == 200, res.text
    report = res.json()["report"]
    assert report["findings"] == [] and report["recommendations"] == []


def _llm_rows(engine, iid):
    with engine.connect() as conn:
        return conn.execute(
            text(
                "SELECT analysis_id, investigation_id, task, provider, model, prompt_version, "
                "attempt, tokens_in, tokens_out, status, error FROM llm_calls "
                "WHERE investigation_id = :i ORDER BY id"
            ),
            {"i": iid},
        ).all()


class UsageGroq(RecordingGroq):
    def complete(self, prompt, *, system=None):
        res = super().complete(prompt, system=system)
        return LLMResult(res.text, tokens_in=123, tokens_out=45, latency_ms=17)


def test_each_llm_call_writes_one_llm_calls_row(
    migrated_engine, settings_for, investigation, monkeypatch
):
    iid, _signal_id, analysis_id, _ids = investigation
    monkeypatch.setattr(investigation_pipeline, "GroqProvider", UsageGroq)
    settings = settings_for.model_copy(update={"groq_api_key": SecretStr("test-groq-key")})

    run_investigation(iid, settings)

    assert _row(migrated_engine, iid).error is None
    (call,) = _llm_rows(migrated_engine, iid)
    assert call.status == "ok" and call.error is None
    assert call.task == "investigation_synthesis"
    assert call.prompt_version == "investigation_synthesis_v1"
    assert (call.provider, call.model, call.attempt) == ("groq", "fake", 1)
    assert (call.tokens_in, call.tokens_out) == (123, 45)
    assert call.analysis_id == analysis_id and call.investigation_id == iid


def test_failed_llm_call_is_logged_and_report_falls_back(
    migrated_engine, settings_for, investigation, client, monkeypatch
):
    iid, *_ = investigation

    class Down:
        model = "down-model"

        def __init__(self, *_a, **_k):
            pass

        def complete(self, prompt, *, system=None):
            raise TimeoutError("provider timed out")

    monkeypatch.setattr(investigation_pipeline, "GroqProvider", Down)
    settings = settings_for.model_copy(update={"groq_api_key": SecretStr("test-groq-key")})
    run_investigation(iid, settings)

    assert _row(migrated_engine, iid).status == "completed"
    (call,) = _llm_rows(migrated_engine, iid)
    assert call.status == "failed" and "provider timed out" in call.error
    assert call.model == "down-model"
    assert client.get(f"/api/v1/investigations/{iid}").json()["report"]["generated_by"] == "fallback"


def test_no_groq_key_means_no_llm_call_rows(migrated_engine, settings_for, investigation):
    iid, *_ = investigation
    run_investigation(iid, settings_for)
    assert _llm_rows(migrated_engine, iid) == []


def test_call_budget_limits_rows(migrated_engine, settings_for, investigation, monkeypatch):
    iid, *_ = investigation
    monkeypatch.setattr(investigation_pipeline, "GroqProvider", RecordingGroq)
    settings = settings_for.model_copy(
        update={"groq_api_key": SecretStr("k"), "llm_max_calls_per_investigation": 0}
    )
    run_investigation(iid, settings)
    assert _llm_rows(migrated_engine, iid) == []  # budget 0: the provider is never called
    assert _row(migrated_engine, iid).status == "completed"


def test_llm_concurrency_setting_reaches_the_shared_limiter(
    migrated_engine, settings_for, investigation, monkeypatch
):
    from app.services.llm.limiter import shared_limiter

    iid, *_ = investigation
    monkeypatch.setattr(investigation_pipeline, "GroqProvider", RecordingGroq)
    settings = settings_for.model_copy(
        update={"groq_api_key": SecretStr("k"), "llm_max_concurrency": 3}
    )
    try:
        run_investigation(iid, settings)
        assert shared_limiter(3).max_concurrency == 3
    finally:
        shared_limiter(1)


def test_confidence_factors_come_from_stored_evidence(
    migrated_engine, settings_for, investigation, client
):
    iid, _signal_id, analysis_id, ids = investigation
    run_investigation(iid, settings_for)
    factors = client.get(f"/api/v1/investigations/{iid}").json()["report"]["confidence"]["factors"]

    # Recompute the expected numbers straight from the rows the report was built from.
    with migrated_engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT e.stance, c.domain, c.published_at FROM evidence e "
                "JOIN content_items c ON c.id = e.content_id WHERE e.investigation_id = :i"
            ),
            {"i": iid},
        ).all()
        as_of = conn.execute(
            text("SELECT as_of_date FROM analyses WHERE id = :a"), {"a": analysis_id}
        ).scalar_one()
    supports = [r for r in rows if r.stance == "supports"]
    contradicts = [r for r in rows if r.stance == "contradicts"]
    assert supports, "scripted complaints should yield supporting evidence"
    assert factors["agreement"] == pytest.approx(
        len(supports) / (len(supports) + len(contradicts)), abs=1e-4
    )
    assert factors["independence"] == pytest.approx(
        min(1, len({r.domain for r in supports}) / 4), abs=1e-4
    )
    ref = datetime.combine(as_of, time.max, tzinfo=UTC)
    credits = [
        0.5 ** (max(0, (ref - r.published_at).total_seconds() / 86400) / 30)
        if r.published_at
        else 0.0
        for r in supports
    ]
    assert factors["recency"] == pytest.approx(sum(credits) / len(credits), abs=1e-3)
    assert factors["recency"] != 0.8  # the old constant
    domains: dict[str, list[int]] = {}
    for r in supports + contradicts:
        domains.setdefault(r.domain, [0, 0])[0 if r.stance == "supports" else 1] += 1
    expected = sum(1 for pro, con in domains.values() if pro > con) / len(domains)
    assert factors["consistency"] == pytest.approx(expected, abs=1e-4)
