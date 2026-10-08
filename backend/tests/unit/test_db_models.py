import io
from pathlib import Path

import pytest
from alembic.config import Config

from alembic import command
from app.db.models import Analysis, AnalysisBrand, Base, Brand
from app.db.models.enums import AnalysisStage, AnalysisStatus, BrandRole

ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"


def _cfg(url: str | None = None) -> Config:
    cfg = Config(str(ALEMBIC_INI))
    if url:
        cfg.attributes["url"] = url
    return cfg


def test_metadata_has_phase_5_and_7_tables():
    assert set(Base.metadata.tables) == {
        "brands",
        "analyses",
        "analysis_brands",
        "serp_cache",
        "serp_usage",
        "raw_items",
        "content_items",
        "content_analysis",
        "item_aspects",
        "trend_points",
        "brand_snapshots",
        "signals",
        "investigations",
        "evidence",
        "recommendations",
        "llm_calls",
    }
    assert Brand.__tablename__ == "brands"
    assert Analysis.__tablename__ == "analyses"
    assert AnalysisBrand.__tablename__ == "analysis_brands"


def test_python_enums_match_database_md_section_3():
    assert [e.value for e in AnalysisStatus] == [
        "queued",
        "running",
        "completed",
        "partial",
        "failed",
    ]
    assert [e.value for e in AnalysisStage] == [
        "planning",
        "collecting",
        "processing",
        "analyzing",
        "detecting",
        "snapshotting",
        "done",
    ]
    assert [e.value for e in BrandRole] == ["target", "competitor", "suggested"]


def test_not_null_columns_follow_database_md():
    cols = Base.metadata.tables["analyses"].c
    not_null = {c.name for c in cols if not c.nullable}
    assert not_null == {
        "id",
        "brand_id",
        "period_days",
        "as_of_date",
        "current_start",
        "current_end",
        "baseline_start",
        "baseline_end",
        "status",
        "progress",
        "warnings",
        "serp_calls_used",
        "serp_calls_budget",
        "live_run",
        "created_at",
    }
    nullable = {c.name for c in cols if c.nullable}
    assert nullable == {
        "product",
        "category",
        "stage",
        "error",
        "client_ip_hash",
        "started_at",
        "finished_at",
    }


def test_alembic_requires_a_database_url(monkeypatch):
    monkeypatch.setenv("DATABASE_URL_DIRECT", "")
    with pytest.raises(RuntimeError, match="DATABASE_URL_DIRECT"):
        command.upgrade(_cfg(), "head")


def test_offline_sql_generation_needs_no_database():
    cfg = _cfg("postgresql://u:p@localhost/none")
    cfg.output_buffer = io.StringIO()
    command.upgrade(cfg, "head", sql=True)
    sql = cfg.output_buffer.getvalue()
    assert "CREATE TYPE analysis_status AS ENUM ('queued', 'running'" in sql
    assert "CREATE TABLE brands" in sql
    assert "CREATE TABLE analyses" in sql
    assert "CREATE TABLE analysis_brands" in sql
    assert "CREATE TABLE content_items" in sql
    assert "CREATE TABLE content_analysis" in sql
    assert "CREATE TABLE item_aspects" in sql
    assert "CREATE TABLE trend_points" in sql
    assert "CREATE TABLE brand_snapshots" in sql
    assert "CREATE TABLE signals" in sql


def test_serp_cache_columns_and_pk():
    table = Base.metadata.tables["serp_cache"]
    assert [c.name for c in table.primary_key.columns] == ["cache_key"]
    assert {c.name for c in table.c if not c.nullable} == {
        "cache_key",
        "engine",
        "params",
        "response",
        "fetched_at",
        "expires_at",
        "pinned",
    }
    assert table.c.http_status.nullable
    assert {i.name for i in table.indexes} == {"ix_serp_cache_expires_at"}


def test_serp_usage_columns_fk_and_constraints():
    table = Base.metadata.tables["serp_usage"]
    assert [c.name for c in table.primary_key.columns] == ["id"]
    assert {c.name for c in table.c if not c.nullable} == {
        "id",
        "cache_key",
        "engine",
        "cache_hit",
        "credits",
        "purpose",
        "account_label",
        "created_at",
    }
    fks = {fk.parent.name: fk for fk in table.foreign_keys}
    assert set(fks) == {"analysis_id", "investigation_id"}
    assert fks["analysis_id"].target_fullname == "analyses.id"
    assert fks["analysis_id"].ondelete == "SET NULL"
    assert fks["investigation_id"].target_fullname == "investigations.id"
    assert fks["investigation_id"].ondelete == "SET NULL"
    assert {i.name for i in table.indexes} == {"ix_serp_usage_created_at"}
    assert {c.name for c in table.constraints if c.name} >= {
        "ck_serp_usage_credits_range",
        "ck_serp_usage_purpose_allowed",
    }
