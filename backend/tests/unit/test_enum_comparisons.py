"""ORM enum members and API enum members are different classes: compare with `==`, never `is`."""

import re
from pathlib import Path

import pytest

from app.db.models import enums as orm_enums
from app.schemas import domain

APP = Path(__file__).resolve().parents[2] / "app"
GUARDED = [APP / "pipeline" / "analysis_pipeline.py", APP / "api" / "v1" / "analyses.py"]
ENUM_NAMES = "BrandRole|WindowKind|ContentPurpose|SourceType|DateConfidence|Sentiment"


@pytest.mark.parametrize("name", ["BrandRole", "WindowKind", "ContentPurpose", "SourceType"])
def test_orm_and_schema_enums_are_equal_but_not_identical(name):
    orm_member = list(getattr(orm_enums, name))[0]
    schema_member = getattr(domain, name)(orm_member.value)
    assert orm_member == schema_member
    assert orm_member is not schema_member


@pytest.mark.parametrize("path", GUARDED, ids=lambda p: p.name)
def test_no_identity_comparison_with_enum_members(path):
    hits = re.findall(rf"\bis (?:not )?(?:{ENUM_NAMES})\.\w+", path.read_text())
    assert hits == []
