import pytest
from pydantic import ValidationError

from app.config.settings import Settings, get_settings


def test_defaults_match_planned_values(make_settings):
    s = make_settings()
    assert s.database_url == ""
    assert s.allow_live_serpapi is False
    assert s.serp_monthly_limit == 250
    assert s.serp_monthly_reserve == 20
    assert s.serp_budget_per_analysis == 12
    assert s.serp_budget_per_investigation == 8
    assert s.serp_cache_ttl_hours == 720
    assert s.max_analyses_per_day == 3
    assert s.max_concurrent_analyses == 1
    assert s.llm_max_concurrency == 1
    assert s.llm_max_calls_per_investigation == 8
    assert s.demo_mode is False
    assert s.log_level == "INFO"
    assert s.sentiment_model == "cardiffnlp/twitter-roberta-base-sentiment-latest"
    assert s.serpapi_account_label == "default"


def test_all_planned_env_vars_are_settings():
    planned = {
        "DATABASE_URL",
        "DATABASE_URL_DIRECT",
        "SERPAPI_API_KEY",
        "SERPAPI_ACCOUNT_LABEL",
        "ALLOW_LIVE_SERPAPI",
        "SERP_MONTHLY_LIMIT",
        "SERP_MONTHLY_RESERVE",
        "SERP_BUDGET_PER_ANALYSIS",
        "SERP_BUDGET_PER_INVESTIGATION",
        "SERP_CACHE_TTL_HOURS",
        "LIVE_ACCESS_CODE",
        "MAX_ANALYSES_PER_DAY",
        "MAX_CONCURRENT_ANALYSES",
        "SENTIMENT_MODEL",
        "HF_HOME",
        "GROQ_API_KEY",
        "GROQ_MODEL",
        "LLM_MAX_CONCURRENCY",
        "LLM_MAX_CALLS_PER_INVESTIGATION",
        "DEMO_MODE",
        "CORS_ORIGINS",
        "LOG_LEVEL",
    }  # PROGRESS.md §21 / DEVELOPMENT_PLAN.md §6
    assert {name.upper() for name in Settings.model_fields} == planned


def test_reads_environment(monkeypatch):
    monkeypatch.setenv("ALLOW_LIVE_SERPAPI", "true")
    monkeypatch.setenv("SERP_MONTHLY_LIMIT", "100")
    monkeypatch.setenv("SERP_MONTHLY_RESERVE", "5")
    monkeypatch.setenv("DEMO_MODE", "1")
    monkeypatch.setenv("LOG_LEVEL", "debug")
    s = Settings(_env_file=None)
    assert s.allow_live_serpapi is True
    assert s.serp_monthly_limit == 100
    assert s.demo_mode is True
    assert s.log_level == "DEBUG"


def test_secrets_are_masked_and_flags_work(make_settings):
    s = make_settings(serpapi_api_key="sk-secret-1", groq_api_key="gq-secret-2")
    assert s.serpapi_configured and s.groq_configured
    assert "sk-secret-1" not in repr(s) and "gq-secret-2" not in repr(s)
    assert "sk-secret-1" not in s.model_dump_json()
    empty = make_settings()
    assert not empty.serpapi_configured and not empty.groq_configured


def test_cors_origins_list(make_settings):
    s = make_settings(cors_origins="http://a.test, http://b.test ,")
    assert s.cors_origins_list == ["http://a.test", "http://b.test"]


def test_invalid_log_level_rejected(make_settings):
    with pytest.raises(ValidationError):
        make_settings(log_level="loud")


def test_reserve_cannot_exceed_limit(make_settings):
    with pytest.raises(ValidationError):
        make_settings(serp_monthly_limit=10, serp_monthly_reserve=20)


def test_concurrency_must_be_positive(make_settings):
    with pytest.raises(ValidationError):
        make_settings(max_concurrent_analyses=0)


def test_get_settings_is_cached():
    get_settings.cache_clear()
    assert get_settings() is get_settings()
    get_settings.cache_clear()
