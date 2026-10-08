"""Synthesizer prompt/citation rules and investigation step states (no DB, no network)."""

import json
import re
from types import SimpleNamespace
from uuid import uuid4

from app.pipeline.investigation_pipeline import _steps
from app.schemas.domain import InvestigationStep, StepState
from app.services.investigation.synthesizer import build_prompt, synthesize
from app.services.llm.base import LLMResult
from app.services.llm.service import LLMService

CONF = {
    "score": 40,
    "label": "low",
    "factors": {
        "independence": 0.25,
        "agreement": 1,
        "signal_strength": 0.8,
        "recency": 0.8,
        "consistency": 1,
    },
}
SIG = SimpleNamespace(aspect="battery", signal_score=0.8)


def _evidence(n=3):
    return [
        SimpleNamespace(
            id=uuid4(),
            stance="supports",
            relevance=0.85,
            note=f"battery drain complaint number {i}",
            rank=i + 1,
        )
        for i in range(n)
    ]


class FakeProvider:
    model = "fake"

    def __init__(self, payload):
        self.payload = payload
        self.prompts = []

    def complete(self, prompt, *, system=None):
        self.prompts.append(prompt)
        text = self.payload if isinstance(self.payload, str) else json.dumps(self.payload)
        return LLMResult(text=text)


def _run(payload, evidence):
    provider = FakeProvider(payload)
    return synthesize(SIG, evidence, CONF, LLMService(provider)), provider


def test_prompt_lists_every_evidence_id_with_note_and_stance():
    ev = _evidence()
    prompt = build_prompt(SIG, ev)
    for e in ev:
        assert str(e.id) in prompt
        assert e.note in prompt
    assert "supports" in prompt
    assert "uncited claims are discarded" in prompt


def test_prompt_is_bounded_and_truncates_long_notes():
    ev = _evidence(40)
    ev[0].note = "x" * 5000
    prompt = build_prompt(SIG, ev)
    assert len(re.findall(r'"id"', prompt)) == 20
    assert "x" * 301 not in prompt


def test_valid_ids_survive_invalid_and_empty_are_dropped():
    ev = _evidence()
    good = str(ev[0].id)
    payload = {
        "summary": "Battery complaints rose.",
        "findings": [
            {"text": "valid", "evidence_ids": [good]},
            {"text": "invented id", "evidence_ids": [str(uuid4())]},
            {"text": "uncited", "evidence_ids": []},
            {"text": "no key at all"},
            {"text": "mixed", "evidence_ids": [good, str(uuid4())]},
            "not a dict",
        ],
        "recommendations": [
            {"title": "t", "action": "a", "rationale": "r", "evidence_ids": [good]},
            {"title": "t", "action": "a", "rationale": "r", "evidence_ids": []},
            {"title": "t", "action": "a", "rationale": "r", "evidence_ids": [str(uuid4())]},
        ],
    }
    report, provider = _run(payload, ev)
    assert report["generated_by"] == "llm"
    assert [f["text"] for f in report["findings"]] == ["valid"]
    assert report["findings"][0]["evidence_ids"] == [good]
    assert len(report["recommendations"]) == 1
    assert report["recommendations"][0]["evidence_ids"] == [good]
    assert str(ev[1].id) in provider.prompts[0]


def test_only_uncited_or_invalid_findings_fall_back_to_cited_fallback_report():
    ev = _evidence()
    payload = {
        "summary": "Looks bad.",
        "findings": [
            {"text": "uncited", "evidence_ids": []},
            {"text": "invented", "evidence_ids": [str(uuid4())]},
        ],
    }
    report, _ = _run(payload, ev)
    assert report["generated_by"] == "fallback"
    valid = {str(e.id) for e in ev}
    assert report["findings"]
    assert all(f["evidence_ids"] and set(f["evidence_ids"]) <= valid for f in report["findings"])


def test_malformed_output_shapes_fall_back():
    ev = _evidence()
    for payload in (
        '{"summary": "x", "findings": "not a list"}',
        '{"findings": [{"text": "t", "evidence_ids": "abc"}], "summary": "s"}',
        '{"summary": 5, "findings": []}',
        "not json at all",
    ):
        report, _ = _run(payload, ev)
        assert report["generated_by"] == "fallback", payload


def test_invalid_scope_is_replaced_with_unknown():
    ev = _evidence()
    payload = {
        "summary": "s",
        "findings": [{"text": "t", "evidence_ids": [str(ev[0].id)]}],
        "scope": {"verdict": "everyone_is_doomed", "explanation": "?"},
    }
    report, _ = _run(payload, ev)
    assert report["generated_by"] == "llm"
    assert report["scope"]["verdict"] == "unknown"


def test_valid_scope_is_kept():
    ev = _evidence()
    scope = {"verdict": "brand_specific", "ratio": 2.0, "explanation": "2x median"}
    payload = {
        "summary": "s",
        "findings": [{"text": "t", "evidence_ids": [str(ev[0].id)]}],
        "scope": scope,
    }
    report, _ = _run(payload, ev)
    assert report["scope"] == scope


def test_no_provider_uses_fallback():
    report = synthesize(SIG, _evidence(), CONF, LLMService(None))
    assert report["generated_by"] == "fallback"


# ---- investigation step states ----


def test_steps_use_api_step_states_only():
    allowed = {s.value for s in StepState}
    keys = [s.value for s in InvestigationStep]
    for step in keys:
        steps = _steps(step)
        assert [x["key"] for x in steps] == keys
        assert {x["state"] for x in steps} <= allowed
        for x in steps:  # every state/key parses through the API enums
            StepState(x["state"])
            InvestigationStep(x["key"])


def test_active_step_is_marked_active_earlier_done_later_pending():
    steps = {x["key"]: x["state"] for x in _steps("collecting_evidence")}
    assert steps["generating_queries"] == "done"
    assert steps["collecting_evidence"] == "active"
    assert steps["scoring_evidence"] == "pending"
    assert "running" not in steps.values() and "completed" not in steps.values()


def test_terminal_done_marks_every_step_done():
    assert {x["state"] for x in _steps("done")} == {"done"}
