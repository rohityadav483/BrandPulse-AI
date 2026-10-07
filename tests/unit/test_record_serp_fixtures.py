"""The fixture recorder must be inert unless explicitly approved. No network, no DB."""

import importlib.util
import json
from pathlib import Path

import pytest

from app.services.serpapi.testing import block_network

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "record_serp_fixtures.py"
BASE = ["--brand", "Samsung", "--product", "Galaxy S25 Ultra", "--as-of", "2026-08-10"]


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    block_network(monkeypatch)


def load_script():
    spec = importlib.util.spec_from_file_location("record_serp_fixtures", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_default_run_is_plan_only(capsys):
    module = load_script()
    module._run_live = lambda *a, **k: pytest.fail("must not go live without --live")
    assert module.main([*BASE, "--competitor", "Apple"]) == 0
    out = capsys.readouterr().out
    assert "9 call(s)" in out and "no credits spent" in out


def test_live_requires_matching_credit_confirmation(capsys):
    module = load_script()
    module._run_live = lambda *a, **k: pytest.fail("must not go live unconfirmed")
    assert module.main([*BASE, "--live"]) == 2
    assert module.main([*BASE, "--live", "--confirm-credits", "3"]) == 2
    assert "Refusing" in capsys.readouterr().out


def test_live_refused_while_the_env_switch_is_off(monkeypatch, capsys):
    module = load_script()

    class Off:
        allow_live_serpapi = False

    monkeypatch.setattr(module, "_load_settings", lambda: Off())
    assert module.main([*BASE, "--live", "--confirm-credits", "7"]) == 2
    assert "ALLOW_LIVE_SERPAPI" in capsys.readouterr().out


def test_recordings_are_sanitized_and_named_stably():
    module = load_script()
    label = "google:target:Samsung:current"
    body = module.wrap_recording(label, {"q": "x"}, {"api_key": "K", "a": 1})
    assert "api_key" not in json.dumps(body) and body["_fixture"]["kind"] == "recorded"
    assert module.fixture_name(3, "google_news:target:Samsung:current") == (
        "recorded_03_google_news_target_samsung_current.json"
    )
