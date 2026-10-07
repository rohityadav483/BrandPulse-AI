import json
import logging

from app.services.nlp import readiness
from app.utils.logging_config import JsonFormatter


def test_nlp_status_unavailable_without_dependencies(monkeypatch):
    monkeypatch.setattr(readiness.importlib.util, "find_spec", lambda name: None)
    assert readiness.nlp_status("model") == "unavailable"


def test_nlp_status_loading_when_dependencies_exist_but_model_not_loaded(monkeypatch):
    monkeypatch.setattr(readiness.importlib.util, "find_spec", lambda name: object())
    monkeypatch.setattr(readiness, "is_loaded", lambda config: False)
    assert readiness.nlp_status("model") == "loading"


def test_nlp_status_ok_when_loaded(monkeypatch):
    monkeypatch.setattr(readiness.importlib.util, "find_spec", lambda name: object())
    monkeypatch.setattr(readiness, "is_loaded", lambda config: True)
    assert readiness.nlp_status("model") == "ok"


def test_json_logging_redacts_secret_fields_and_database_password():
    record = logging.LogRecord("x", logging.ERROR, __file__, 1, "failed", (), None)
    record.api_key = "sk-secret"
    record.access_code = "door-code"
    record.database_url = "postgresql://user:db-secret@host/db"
    payload = json.loads(JsonFormatter().format(record))
    rendered = json.dumps(payload)
    assert "sk-secret" not in rendered
    assert "door-code" not in rendered
    assert "db-secret" not in rendered
    assert payload["api_key"] == "[REDACTED]"
