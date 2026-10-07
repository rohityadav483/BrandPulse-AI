"""Python mirrors of the Postgres enums in docs/DATABASE.md section 3.

Only enums used by existing models are mirrored. The migration creates all of them.
"""

import enum

from sqlalchemy.dialects.postgresql import ENUM


class AnalysisStatus(enum.StrEnum):
    queued = "queued"
    running = "running"
    completed = "completed"
    partial = "partial"
    failed = "failed"


class AnalysisStage(enum.StrEnum):
    planning = "planning"
    collecting = "collecting"
    processing = "processing"
    analyzing = "analyzing"
    detecting = "detecting"
    snapshotting = "snapshotting"
    done = "done"


class BrandRole(enum.StrEnum):
    target = "target"
    competitor = "competitor"
    suggested = "suggested"


class SourceType(enum.StrEnum):
    web = "web"
    news = "news"
    youtube = "youtube"
    forum = "forum"
    shopping = "shopping"


class WindowKind(enum.StrEnum):
    baseline = "baseline"
    current = "current"


class ContentPurpose(enum.StrEnum):
    collection = "collection"
    investigation = "investigation"


def pg_enum(py_enum: type[enum.StrEnum], name: str) -> ENUM:
    """Column type for an existing Postgres enum (the migration owns CREATE TYPE)."""
    return ENUM(
        py_enum,
        name=name,
        values_callable=lambda e: [member.value for member in e],
        create_type=False,
    )
