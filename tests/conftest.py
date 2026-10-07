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


# ---------- Phase 3.2 helpers: StoredRawItem builders (no DB, no network) ----------

import json  # noqa: E402
import uuid  # noqa: E402
from datetime import UTC, datetime  # noqa: E402
from pathlib import Path  # noqa: E402

from app.schemas.domain import ContentPurpose, WindowKind  # noqa: E402
from app.schemas.serp import QuerySpec, RawItem, SerpEngine, StoredRawItem  # noqa: E402
from app.services.serpapi.cache import cache_key as _serp_cache_key  # noqa: E402
from app.services.serpapi.parsers import parse_response  # noqa: E402

SERP_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "serpapi"
CONTENT_FIXTURE_FILES = {
    SerpEngine.google: "google_web_samsung_s25_ultra.json",
    SerpEngine.google_news: "google_news_samsung_s25_ultra.json",
    SerpEngine.google_forums: "google_forums_samsung_s25_ultra.json",
    SerpEngine.youtube: "youtube_samsung_s25_ultra.json",
}
COLLECTED_AT = datetime(2026, 8, 10, 12, 0, tzinfo=UTC)


@pytest.fixture
def stored_raw():
    """Factory: RawItem -> StoredRawItem as `raw_items` would return it."""

    def _make(
        item: RawItem,
        *,
        analysis_id: uuid.UUID,
        brand_id: uuid.UUID,
        purpose: ContentPurpose = ContentPurpose.collection,
        window: WindowKind | None = WindowKind.current,
        collected_at: datetime = COLLECTED_AT,
    ) -> StoredRawItem:
        if purpose is ContentPurpose.investigation:
            window = None
        return StoredRawItem(
            **item.model_dump(),
            id=uuid.uuid4(),
            analysis_id=analysis_id,
            brand_id=brand_id,
            purpose=purpose,
            window=window,
            raw_key=item.compute_raw_key(),
            collected_at=collected_at,
        )

    return _make


@pytest.fixture
def fixture_raw_items():
    """Factory: engine -> the RawItems its synthetic fixture parses to."""

    def _load(engine: SerpEngine, query: str = "Samsung Galaxy S25 Ultra") -> list[RawItem]:
        param = "search_query" if engine is SerpEngine.youtube else "q"
        spec = QuerySpec(engine=engine, params={param: query})
        response = json.loads(
            (SERP_FIXTURES / CONTENT_FIXTURE_FILES[engine]).read_text(encoding="utf-8")
        )
        key = _serp_cache_key(spec.engine, spec.params)
        return parse_response(spec, response, cache_key=key).items

    return _load
