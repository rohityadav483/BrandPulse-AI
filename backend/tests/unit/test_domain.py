"""Shared enums stay identical to docs/DATABASE.md section 3 and to the DB model mirrors."""

import re
from pathlib import Path

import pytest

from app.db.models import enums as db_enums
from app.schemas import domain

DATABASE_MD = Path(__file__).resolve().parents[3] / "docs" / "DATABASE.md"

# Postgres enum name (DATABASE.md section 3) -> API-side enum class.
PG_ENUMS = {
    "analysis_status": domain.AnalysisStatus,
    "analysis_stage": domain.AnalysisStage,
    "brand_role": domain.BrandRole,
    "source_type": domain.SourceType,
    "window_kind": domain.WindowKind,
    "content_purpose": domain.ContentPurpose,
    "date_confidence": domain.DateConfidence,
    "sentiment": domain.Sentiment,
    "signal_kind": domain.SignalKind,
    "impact_level": domain.ImpactLevel,
    "signal_status": domain.SignalStatus,
    "investigation_status": domain.InvestigationStatus,
    "investigation_step": domain.InvestigationStep,
    "scope_verdict": domain.ScopeVerdict,
    "stance": domain.Stance,
    "priority": domain.Priority,
}


def _doc_enums() -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    text = DATABASE_MD.read_text(encoding="utf-8")
    section = text.split("## 3. Enumerations", 1)[1].split("\n## 4.", 1)[0]
    for line in section.splitlines():
        match = re.match(r"\|\s*`([a-z_]+)`\s*\|(.+)\|\s*$", line)
        if match:
            found[match.group(1)] = re.findall(r"`([a-z_]+)`", match.group(2))
    return found


DOC_ENUMS = _doc_enums()


def test_database_md_table_was_parsed():
    assert len(DOC_ENUMS) >= 17


@pytest.mark.parametrize("pg_name", sorted(PG_ENUMS))
def test_enum_values_match_database_md(pg_name):
    expected = DOC_ENUMS[pg_name]
    if pg_name == "signal_kind":
        expected = expected[
            :1
        ]  # `topic_surge` is documented as reserved, not in the MVP
    assert [m.value for m in PG_ENUMS[pg_name]] == expected


@pytest.mark.parametrize(
    "name",
    [
        "AnalysisStatus",
        "AnalysisStage",
        "BrandRole",
        "SourceType",
        "WindowKind",
        "ContentPurpose",
        "DateConfidence",
    ],
)
def test_enums_match_db_model_mirrors(name):
    api_values = [m.value for m in getattr(domain, name)]
    db_values = [m.value for m in getattr(db_enums, name)]
    assert api_values == db_values


@pytest.mark.parametrize(
    ("score", "label"),
    [
        (0, "low"),
        (39, "low"),
        (39.9, "low"),
        (40, "medium"),
        (69, "medium"),
        (70, "high"),
        (100, "high"),
    ],
)
def test_confidence_label_thresholds(score, label):
    assert domain.confidence_label(score) == label


def test_api_only_vocabularies():
    assert [m.value for m in domain.ConfidenceSource] == ["signal", "investigation"]
    assert [m.value for m in domain.GeneratedBy] == ["llm", "fallback"]
    assert [m.value for m in domain.Category] == ["consumer_electronics", "generic"]
    assert [m.value for m in domain.StepState] == ["done", "active", "pending"]
    assert [m.value for m in domain.BlockedReason] == [
        "serpapi_quota_low",
        "live_data_disabled",
        "daily_limit_reached",
    ]
    assert "trends" in {m.value for m in domain.CoverageSourceType}
    assert {m.value for m in domain.SourceType} < {
        m.value for m in domain.CoverageSourceType
    }
