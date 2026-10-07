"""`content_analysis` access, with its `item_aspects`, and reuse by `(content_hash,
analyzer_version)` (Phase 4.2).

Results are never overwritten: an item that already has a row is skipped. Reuse copies the
model-derived results (sentiment, scores, topics, keywords, model, aspects) of an earlier
analysis of the same text under the same `analyzer_version`; relevance is brand-specific, so the
copy takes the caller's `matched_terms` and is always `is_about_brand = true`. Only sources that
are about their brand are reusable, because only those went through inference.

Like the other repositories this takes an `Engine`; each call is one transaction on its own
session. Nothing here runs a model. Only `pipeline/` constructs and wires it.
"""

import uuid
from collections.abc import Iterable, Sequence

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.db.models.content_analysis import ContentAnalysisRow
from app.db.models.content_item import ContentItemRow
from app.db.models.item_aspect import ItemAspectRow
from app.db.repositories.item_aspect import aspect_values, to_aspect
from app.schemas.nlp import (
    AnalysisWriteResult,
    ItemAnalysis,
    NewItemAnalysis,
    ReuseResult,
    ReuseTarget,
    StoredItemAnalysis,
)


def _analysis_values(
    content_id: uuid.UUID, content_hash: str, analysis: ItemAnalysis, **extra
) -> dict:
    return {
        "content_id": content_id,
        "content_hash": content_hash,
        "sentiment": analysis.sentiment,
        "sentiment_score": analysis.sentiment_score,
        "negative_prob": analysis.negative_prob,
        "is_about_brand": analysis.is_about_brand,
        "matched_terms": list(analysis.matched_terms),
        "topics": list(analysis.topics),
        "keywords": list(analysis.keywords),
        "model": analysis.model,
        "analyzer_version": analysis.analyzer_version,
    } | extra


def _stored(row: ContentAnalysisRow, aspects: Sequence[ItemAspectRow]) -> StoredItemAnalysis:
    return StoredItemAnalysis(
        content_id=row.content_id,
        content_hash=row.content_hash,
        analyzed_at=row.analyzed_at,
        analysis=ItemAnalysis(
            sentiment=row.sentiment,
            sentiment_score=row.sentiment_score,
            negative_prob=row.negative_prob,
            is_about_brand=row.is_about_brand,
            matched_terms=tuple(row.matched_terms),
            topics=tuple(row.topics),
            keywords=tuple(row.keywords),
            model=row.model,
            analyzer_version=row.analyzer_version,
            aspects=tuple(to_aspect(a) for a in sorted(aspects, key=lambda a: a.aspect)),
        ),
    )


def _aspects_by_content(
    session: Session, content_ids: Iterable[uuid.UUID]
) -> dict[uuid.UUID, list[ItemAspectRow]]:
    ids = list(content_ids)
    grouped: dict[uuid.UUID, list[ItemAspectRow]] = {}
    if not ids:
        return grouped
    statement = select(ItemAspectRow).where(ItemAspectRow.content_id.in_(ids))
    for row in session.execute(statement).scalars():
        grouped.setdefault(row.content_id, []).append(row)
    return grouped


def _reusable_sources(
    session: Session, content_hashes: Iterable[str], analyzer_version: str
) -> dict[str, ContentAnalysisRow]:
    """Per content hash, the earliest analysis (then lowest content id) under the version
    whose item is about its brand. Deterministic, one query."""
    wanted = set(content_hashes)
    if not wanted:
        return {}
    statement = (
        select(ContentAnalysisRow)
        .where(
            ContentAnalysisRow.content_hash.in_(wanted),
            ContentAnalysisRow.analyzer_version == analyzer_version,
            ContentAnalysisRow.is_about_brand.is_(True),
        )
        .distinct(ContentAnalysisRow.content_hash)
        .order_by(
            ContentAnalysisRow.content_hash,
            ContentAnalysisRow.analyzed_at,
            ContentAnalysisRow.content_id,
        )
    )
    return {row.content_hash: row for row in session.execute(statement).scalars()}


class ContentAnalysisRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    # ---- create ----

    def save_many(self, items: Sequence[NewItemAnalysis]) -> AnalysisWriteResult:
        """Persist analyses and their aspects in one transaction (all or nothing).

        An item that already has an analysis is skipped, aspects included. A `content_id` that
        is not a stored content item raises `IntegrityError` and nothing is written.
        """
        if not items:
            return AnalysisWriteResult(inserted=0, skipped=0)
        by_id = {item.content_id: item for item in items}
        if len(by_id) != len(items):
            raise ValueError("duplicate content_id in one save_many call")
        statement = (
            pg_insert(ContentAnalysisRow)
            .values([_analysis_values(i.content_id, i.content_hash, i.analysis) for i in items])
            .on_conflict_do_nothing(index_elements=[ContentAnalysisRow.content_id])
            .returning(ContentAnalysisRow.content_id)
        )
        with Session(self._engine) as session, session.begin():
            inserted_ids = list(session.execute(statement).scalars())
            aspect_rows = [
                aspect_values(content_id, aspect)
                for content_id in inserted_ids
                for aspect in by_id[content_id].analysis.aspects
            ]
            if aspect_rows:
                session.execute(pg_insert(ItemAspectRow).values(aspect_rows))
        return AnalysisWriteResult(
            inserted=len(inserted_ids),
            skipped=len(items) - len(inserted_ids),
            inserted_ids=tuple(inserted_ids),
        )

    # ---- retrieve ----

    def get(self, content_id: uuid.UUID) -> StoredItemAnalysis | None:
        return self.get_many([content_id]).get(content_id)

    def get_many(self, content_ids: Iterable[uuid.UUID]) -> dict[uuid.UUID, StoredItemAnalysis]:
        ids = list(set(content_ids))
        if not ids:
            return {}
        with Session(self._engine) as session:
            rows = session.execute(
                select(ContentAnalysisRow).where(ContentAnalysisRow.content_id.in_(ids))
            ).scalars()
            rows = list(rows)
            aspects = _aspects_by_content(session, (row.content_id for row in rows))
            return {row.content_id: _stored(row, aspects.get(row.content_id, ())) for row in rows}

    def list_for_analysis(
        self,
        analysis_id: uuid.UUID,
        *,
        brand_id: uuid.UUID | None = None,
        is_about_brand: bool | None = None,
    ) -> list[StoredItemAnalysis]:
        """Analyses of an analysis' content items. Stable order: content id."""
        statement = (
            select(ContentAnalysisRow)
            .join(ContentItemRow, ContentItemRow.id == ContentAnalysisRow.content_id)
            .where(ContentItemRow.analysis_id == analysis_id)
            .order_by(ContentAnalysisRow.content_id)
        )
        if brand_id is not None:
            statement = statement.where(ContentItemRow.brand_id == brand_id)
        if is_about_brand is not None:
            statement = statement.where(ContentAnalysisRow.is_about_brand.is_(is_about_brand))
        with Session(self._engine) as session:
            rows = list(session.execute(statement).scalars())
            aspects = _aspects_by_content(session, (row.content_id for row in rows))
            return [_stored(row, aspects.get(row.content_id, ())) for row in rows]

    def count_for_analysis(
        self,
        analysis_id: uuid.UUID,
        *,
        brand_id: uuid.UUID | None = None,
        is_about_brand: bool | None = None,
    ) -> int:
        statement = (
            select(func.count())
            .select_from(ContentAnalysisRow)
            .join(ContentItemRow, ContentItemRow.id == ContentAnalysisRow.content_id)
            .where(ContentItemRow.analysis_id == analysis_id)
        )
        if brand_id is not None:
            statement = statement.where(ContentItemRow.brand_id == brand_id)
        if is_about_brand is not None:
            statement = statement.where(ContentAnalysisRow.is_about_brand.is_(is_about_brand))
        with Session(self._engine) as session:
            return session.execute(statement).scalar_one()

    # ---- check ----

    def analyzed_content_ids(self, content_ids: Iterable[uuid.UUID]) -> set[uuid.UUID]:
        """The subset of `content_ids` that already has an analysis row."""
        ids = set(content_ids)
        if not ids:
            return set()
        statement = select(ContentAnalysisRow.content_id).where(
            ContentAnalysisRow.content_id.in_(ids)
        )
        with Session(self._engine) as session:
            return set(session.execute(statement).scalars())

    # ---- reuse by (content_hash, analyzer_version) ----

    def find_reusable(
        self, content_hashes: Iterable[str], analyzer_version: str
    ) -> dict[str, uuid.UUID]:
        """`content_hash -> content_id` of an existing analysis that can be copied."""
        with Session(self._engine) as session:
            sources = _reusable_sources(session, content_hashes, analyzer_version)
        return {content_hash: row.content_id for content_hash, row in sources.items()}

    def copy_reusable(self, targets: Sequence[ReuseTarget], analyzer_version: str) -> ReuseResult:
        """Copy earlier results onto `targets` without inference, in one transaction.

        Targets that already have a row are left alone (`already_analyzed`); targets with no
        reusable source are returned in `missing` and must be analyzed by the model.
        """
        if not targets:
            return ReuseResult()
        if len({t.content_id for t in targets}) != len(targets):
            raise ValueError("duplicate content_id in one copy_reusable call")
        reused: list[uuid.UUID] = []
        missing: list[uuid.UUID] = []
        already: list[uuid.UUID] = []
        with Session(self._engine) as session, session.begin():
            existing = set(
                session.execute(
                    select(ContentAnalysisRow.content_id).where(
                        ContentAnalysisRow.content_id.in_([t.content_id for t in targets])
                    )
                ).scalars()
            )
            todo = [t for t in targets if t.content_id not in existing]
            already = [t.content_id for t in targets if t.content_id in existing]
            sources = _reusable_sources(session, (t.content_hash for t in todo), analyzer_version)
            source_aspects = _aspects_by_content(session, (r.content_id for r in sources.values()))
            analysis_rows: list[dict] = []
            aspect_rows: list[dict] = []
            for target in todo:
                source = sources.get(target.content_hash)
                if source is None:
                    missing.append(target.content_id)
                    continue
                analysis_rows.append(
                    {
                        "content_id": target.content_id,
                        "content_hash": target.content_hash,
                        "sentiment": source.sentiment,
                        "sentiment_score": source.sentiment_score,
                        "negative_prob": source.negative_prob,
                        "is_about_brand": True,
                        "matched_terms": list(target.matched_terms),
                        "topics": list(source.topics),
                        "keywords": list(source.keywords),
                        "model": source.model,
                        "analyzer_version": source.analyzer_version,
                        "analyzed_at": source.analyzed_at,
                    }
                )
                aspect_rows.extend(
                    aspect_values(target.content_id, to_aspect(a))
                    for a in source_aspects.get(source.content_id, ())
                )
                reused.append(target.content_id)
            if analysis_rows:
                session.execute(pg_insert(ContentAnalysisRow).values(analysis_rows))
            if aspect_rows:
                session.execute(pg_insert(ItemAspectRow).values(aspect_rows))
        return ReuseResult(
            reused=tuple(reused), missing=tuple(missing), already_analyzed=tuple(already)
        )
