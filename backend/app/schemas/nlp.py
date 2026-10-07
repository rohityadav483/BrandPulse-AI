"""Phase 4.2 value types for persisted NLP results (docs/DATABASE.md sections 5.6 and 5.7).

Pure Pydantic, no DB, no I/O. They are the shapes `services/nlp/item_analysis` produces and
`db/repositories/content_analysis` / `item_aspect` store and return. Scores follow the
documented ranges: `sentiment_score` and aspect `score` in [-1, 1], probabilities in [0, 1].
"""

import re
from datetime import datetime
from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.domain import Sentiment

_SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")


def _not_blank(value: str) -> str:
    if not value.strip():
        raise ValueError("must not be blank")
    return value


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True)


class AspectSentiment(_Frozen):
    """One `item_aspects` row without its content id: the analyzed clause and its sentiment."""

    aspect: str
    clause: str
    sentiment: Sentiment
    negative_prob: float = Field(ge=0.0, le=1.0)
    score: float = Field(ge=-1.0, le=1.0)

    _check_aspect = field_validator("aspect")(_not_blank)
    _check_clause = field_validator("clause")(_not_blank)


class ItemAnalysis(_Frozen):
    """One `content_analysis` row without its identity, plus the item's aspect rows.

    `keywords` and `topics` come from the deterministic rules in `services/nlp/keywords.py` and
    `topics.py`; both are empty for items that are not about the brand.
    """

    sentiment: Sentiment
    sentiment_score: float = Field(ge=-1.0, le=1.0)
    negative_prob: float = Field(ge=0.0, le=1.0)
    is_about_brand: bool
    matched_terms: tuple[str, ...] = ()
    topics: tuple[str, ...] = ()
    keywords: tuple[str, ...] = ()
    model: str
    analyzer_version: str
    aspects: tuple[AspectSentiment, ...] = ()

    _check_model = field_validator("model")(_not_blank)
    _check_version = field_validator("analyzer_version")(_not_blank)

    @model_validator(mode="after")
    def _aspects_are_unique(self) -> Self:
        names = [a.aspect for a in self.aspects]
        if len(set(names)) != len(names):
            raise ValueError("aspects must be unique per item (PK is content_id, aspect)")
        return self


class NewItemAnalysis(_Frozen):
    """What a repository writes: the analysis of one stored content item."""

    content_id: UUID
    content_hash: str
    analysis: ItemAnalysis

    @field_validator("content_hash")
    @classmethod
    def _sha256(cls, value: str) -> str:
        if not _SHA256_HEX.match(value):
            raise ValueError("content_hash must be a lowercase sha256 hex digest")
        return value


class StoredItemAnalysis(_Frozen):
    """A persisted `content_analysis` row with its `item_aspects`."""

    content_id: UUID
    content_hash: str
    analyzed_at: datetime
    analysis: ItemAnalysis


class StoredItemAspect(_Frozen):
    content_id: UUID
    aspect: AspectSentiment


class AnalysisWriteResult(_Frozen):
    """`skipped` = content items that already had an analysis row (never overwritten)."""

    inserted: int
    skipped: int
    inserted_ids: tuple[UUID, ...] = ()


class ReuseTarget(_Frozen):
    """An item that is about the brand and needs analysis under one `analyzer_version`.

    Only model-derived results are copied from an earlier analysis of the same text.
    Relevance depends on the brand, so the caller's own `matched_terms` are used.
    """

    content_id: UUID
    content_hash: str
    matched_terms: tuple[str, ...] = ()

    @field_validator("content_hash")
    @classmethod
    def _sha256(cls, value: str) -> str:
        if not _SHA256_HEX.match(value):
            raise ValueError("content_hash must be a lowercase sha256 hex digest")
        return value


class ReuseResult(_Frozen):
    """`reused`: copied from an earlier analysis (zero inference). `missing`: no reusable
    source, needs inference. `already_analyzed`: target already had a row, left untouched."""

    reused: tuple[UUID, ...] = ()
    missing: tuple[UUID, ...] = ()
    already_analyzed: tuple[UUID, ...] = ()
