"""`item_aspects` access: aspect-clause sentiment rows of content items (Phase 4.2).

Rows are never updated: a repeat `(content_id, aspect)` is skipped. Like the other repositories
this takes an `Engine` and runs each call in one short transaction. Writing an item's analysis
together with its aspects is `ContentAnalysisRepository.save_many` (one transaction).
"""

import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from sqlalchemy.sql import Select

from app.db.models.content_item import ContentItemRow
from app.db.models.item_aspect import ItemAspectRow
from app.schemas.domain import Sentiment, WindowKind
from app.schemas.nlp import AspectSentiment, StoredItemAspect


def aspect_values(content_id: uuid.UUID, aspect: AspectSentiment) -> dict:
    return {
        "content_id": content_id,
        "aspect": aspect.aspect,
        "clause": aspect.clause,
        "sentiment": aspect.sentiment,
        "negative_prob": aspect.negative_prob,
        "score": aspect.score,
    }


def to_aspect(row: ItemAspectRow) -> AspectSentiment:
    return AspectSentiment(
        aspect=row.aspect,
        clause=row.clause,
        sentiment=row.sentiment,
        negative_prob=row.negative_prob,
        score=row.score,
    )


def _joined(
    statement: Select,
    analysis_id: uuid.UUID,
    brand_id: uuid.UUID | None,
    window: WindowKind | None,
    aspect: str | None,
    sentiment: Sentiment | None,
) -> Select:
    statement = statement.join(ContentItemRow, ContentItemRow.id == ItemAspectRow.content_id).where(
        ContentItemRow.analysis_id == analysis_id
    )
    if brand_id is not None:
        statement = statement.where(ContentItemRow.brand_id == brand_id)
    if window is not None:
        statement = statement.where(ContentItemRow.window == window)
    if aspect is not None:
        statement = statement.where(ItemAspectRow.aspect == aspect)
    if sentiment is not None:
        statement = statement.where(ItemAspectRow.sentiment == sentiment)
    return statement


class ItemAspectRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def add_many(self, content_id: uuid.UUID, aspects: Sequence[AspectSentiment]) -> int:
        """Store aspect rows of one item in one transaction. Returns how many were inserted
        (existing `(content_id, aspect)` pairs are skipped)."""
        if not aspects:
            return 0
        statement = (
            pg_insert(ItemAspectRow)
            .values([aspect_values(content_id, aspect) for aspect in aspects])
            .on_conflict_do_nothing(index_elements=[ItemAspectRow.content_id, ItemAspectRow.aspect])
            .returning(ItemAspectRow.aspect)
        )
        with Session(self._engine) as session, session.begin():
            return len(list(session.execute(statement).scalars()))

    def list_for_content(self, content_id: uuid.UUID) -> list[AspectSentiment]:
        """Aspect rows of one item, ordered by aspect name."""
        statement = (
            select(ItemAspectRow)
            .where(ItemAspectRow.content_id == content_id)
            .order_by(ItemAspectRow.aspect)
        )
        with Session(self._engine) as session:
            return [to_aspect(row) for row in session.execute(statement).scalars()]

    def list_for_analysis(
        self,
        analysis_id: uuid.UUID,
        *,
        brand_id: uuid.UUID | None = None,
        window: WindowKind | None = None,
        aspect: str | None = None,
        sentiment: Sentiment | None = None,
    ) -> list[StoredItemAspect]:
        """Aspect rows of an analysis' content items. Stable order: aspect, content id."""
        statement = _joined(
            select(ItemAspectRow), analysis_id, brand_id, window, aspect, sentiment
        ).order_by(ItemAspectRow.aspect, ItemAspectRow.content_id)
        with Session(self._engine) as session:
            return [
                StoredItemAspect(content_id=row.content_id, aspect=to_aspect(row))
                for row in session.execute(statement).scalars()
            ]

    def count(
        self,
        analysis_id: uuid.UUID,
        *,
        brand_id: uuid.UUID | None = None,
        window: WindowKind | None = None,
        aspect: str | None = None,
        sentiment: Sentiment | None = None,
    ) -> int:
        statement = _joined(
            select(func.count()).select_from(ItemAspectRow),
            analysis_id,
            brand_id,
            window,
            aspect,
            sentiment,
        )
        with Session(self._engine) as session:
            return session.execute(statement).scalar_one()
