import pytest
from fastapi.testclient import TestClient

from app.config.settings import Settings
from app.db.session import dispose_engines
from app.main import create_app

_SETTING_ENV_VARS = [name.upper() for name in Settings.model_fields]


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Tests never depend on the developer's real environment or .env file."""
    for name in _SETTING_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    yield
    dispose_engines()


@pytest.fixture
def make_settings():
    def _make(**overrides) -> Settings:
        return Settings(_env_file=None, **overrides)

    return _make


@pytest.fixture
def make_client(make_settings):
    def _make(**overrides) -> TestClient:
        app = create_app(make_settings(**overrides))
        return TestClient(app, raise_server_exceptions=False)

    return _make
