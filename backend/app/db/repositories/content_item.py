"""`content_items` access: create, retrieve and check normalized items (Phase 3.2).

No cleaning, normalization or dedupe decisions happen here (those are `services/processing`).
The unique index on `(analysis_id, brand_id, content_hash)` is a last line of defence: a repeat
is skipped and reported as `duplicates`, never updated.

Like the other repositories this takes an `Engine` and runs each call in one short transaction
on its own session, so a batch is all-or-nothing. Only `pipeline/` constructs and wires it.
"""

import uuid
from collections.abc import Iterable, Sequence

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from sqlalchemy.sql import Select

from app.db.models.content_item import ContentItemRow
from app.schemas.domain import ContentPurpose, SourceType, WindowKind
from app.schemas.processing import ContentItem, ContentWriteResult, StoredContentItem

_IDENTITY = [
    ContentItemRow.analysis_id,
    ContentItemRow.brand_id,
    ContentItemRow.content_hash,
]


def _values(analysis_id: uuid.UUID, brand_id: uuid.UUID, item: ContentItem) -> dict:
    return {
        "analysis_id": analysis_id,
        "brand_id": brand_id,
        "purpose": item.purpose,
        "window": item.window,
        "source_type": item.source_type,
        "engine": item.engine.value,
        "url": item.url,
        "url_hash": item.url_hash,
        "domain": item.domain,
        "title": item.title,
        "snippet": item.snippet,
        "author": item.author,
        "published_at": item.published_at,
        "date_confidence": item.date_confidence,
        "query": item.query,
        "item_metadata": item.metadata,
        "content_hash": item.content_hash,
        "dup_group": item.dup_group,
        "serp_cache_key": item.serp_cache_key,
        "collected_at": item.collected_at,
    }


def _to_stored(row: ContentItemRow) -> StoredContentItem:
    return StoredContentItem(
        id=row.id,
        analysis_id=row.analysis_id,
        brand_id=row.brand_id,
        purpose=row.purpose,
        window=row.window,
        source_type=row.source_type,
        engine=row.engine,
        url=row.url,
        url_hash=row.url_hash,
        domain=row.domain,
        title=row.title,
        snippet=row.snippet,
        author=row.author,
        published_at=row.published_at,
        date_confidence=row.date_confidence,
        query=row.query,
        metadata=row.item_metadata,
        content_hash=row.content_hash,
        dup_group=row.dup_group,
        serp_cache_key=row.serp_cache_key,
        collected_at=row.collected_at,
    )


def _filtered(
    statement: Select,
    analysis_id: uuid.UUID,
    brand_id: uuid.UUID | None,
    purpose: ContentPurpose | None,
    window: WindowKind | None,
    source_type: SourceType | None,
) -> Select:
    statement = statement.where(ContentItemRow.analysis_id == analysis_id)
    if brand_id is not None:
        statement = statement.where(ContentItemRow.brand_id == brand_id)
    if purpose is not None:
        statement = statement.where(ContentItemRow.purpose == purpose)
    if window is not None:
        statement = statement.where(ContentItemRow.window == window)
    if source_type is not None:
        statement = statement.where(ContentItemRow.source_type == source_type)
    return statement


class ContentItemRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    # ---- create ----

    def add_many(
        self, analysis_id: uuid.UUID, brand_id: uuid.UUID, items: Sequence[ContentItem]
    ) -> ContentWriteResult:
        """Persist a batch in one transaction. Repeats (same content hash) are skipped."""
        if not items:
            return ContentWriteResult(inserted=0, duplicates=0)
        statement = (
            pg_insert(ContentItemRow)
            .values([_values(analysis_id, brand_id, item) for item in items])
            .on_conflict_do_nothing(index_elements=_IDENTITY)
            .returning(ContentItemRow.id)
        )
        with Session(self._engine) as session, session.begin():
            inserted_ids = list(session.execute(statement).scalars())
        return ContentWriteResult(
            inserted=len(inserted_ids),
            duplicates=len(items) - len(inserted_ids),
            inserted_ids=inserted_ids,
        )

    def add(
        self, analysis_id: uuid.UUID, brand_id: uuid.UUID, item: ContentItem
    ) -> tuple[StoredContentItem, bool]:
        """Persist one item. Returns (stored row, created); `created` is False for a repeat."""
        statement = (
            pg_insert(ContentItemRow)
            .values(**_values(analysis_id, brand_id, item))
            .on_conflict_do_nothing(index_elements=_IDENTITY)
            .returning(ContentItemRow.id)
        )
        with Session(self._engine) as session, session.begin():
            new_id = session.execute(statement).scalar_one_or_none()
            if new_id is not None:
                return _to_stored(session.get_one(ContentItemRow, new_id)), True
            existing = session.execute(
                select(ContentItemRow).where(
                    ContentItemRow.analysis_id == analysis_id,
                    ContentItemRow.brand_id == brand_id,
                    ContentItemRow.content_hash == item.content_hash,
                )
            ).scalar_one()
            return _to_stored(existing), False

    # ---- retrieve ----

    def get(self, content_item_id: uuid.UUID) -> StoredContentItem | None:
        with Session(self._engine) as session:
            row = session.get(ContentItemRow, content_item_id)
            return _to_stored(row) if row is not None else None

    def list_for_analysis(
        self,
        analysis_id: uuid.UUID,
        *,
        brand_id: uuid.UUID | None = None,
        purpose: ContentPurpose | None = None,
        window: WindowKind | None = None,
        source_type: SourceType | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[StoredContentItem]:
        """Items of an analysis, optionally filtered. Stable order: collected_at, engine, url,
        id."""
        statement = _filtered(
            select(ContentItemRow), analysis_id, brand_id, purpose, window, source_type
        ).order_by(
            ContentItemRow.collected_at,
            ContentItemRow.engine,
            ContentItemRow.url,
            ContentItemRow.id,
        )
        if limit is not None:
            statement = statement.limit(limit)
        if offset:
            statement = statement.offset(offset)
        with Session(self._engine) as session:
            return [_to_stored(row) for row in session.execute(statement).scalars()]

    def count(
        self,
        analysis_id: uuid.UUID,
        *,
        brand_id: uuid.UUID | None = None,
        purpose: ContentPurpose | None = None,
        window: WindowKind | None = None,
        source_type: SourceType | None = None,
    ) -> int:
        statement = _filtered(
            select(func.count()).select_from(ContentItemRow),
            analysis_id,
            brand_id,
            purpose,
            window,
            source_type,
        )
        with Session(self._engine) as session:
            return session.execute(statement).scalar_one()

    def count_dup_groups(
        self, analysis_id: uuid.UUID, *, brand_id: uuid.UUID | None = None
    ) -> int:
        """Distinct `dup_group` values (independent sources) among an analysis' items."""
        statement = select(func.count(func.distinct(ContentItemRow.dup_group))).where(
            ContentItemRow.analysis_id == analysis_id
        )
        if brand_id is not None:
            statement = statement.where(ContentItemRow.brand_id == brand_id)
        with Session(self._engine) as session:
            return session.execute(statement).scalar_one()

    # ---- check ----

    def existing_content_hashes(
        self, analysis_id: uuid.UUID, brand_id: uuid.UUID, hashes: Iterable[str]
    ) -> set[str]:
        """The subset of `hashes` already stored (one query; empty input = no query)."""
        wanted = set(hashes)
        if not wanted:
            return set()
        statement = select(ContentItemRow.content_hash).where(
            ContentItemRow.analysis_id == analysis_id,
            ContentItemRow.brand_id == brand_id,
            ContentItemRow.content_hash.in_(wanted),
        )
        with Session(self._engine) as session:
            return set(session.execute(statement).scalars())

    def existing_url_hashes(
        self, analysis_id: uuid.UUID, brand_id: uuid.UUID, hashes: Iterable[str]
    ) -> set[str]:
        wanted = set(hashes)
        if not wanted:
            return set()
        statement = select(ContentItemRow.url_hash).where(
            ContentItemRow.analysis_id == analysis_id,
            ContentItemRow.brand_id == brand_id,
            ContentItemRow.url_hash.in_(wanted),
        )
        with Session(self._engine) as session:
            return set(session.execute(statement).scalars())

    def stored_hashes(
        self, analysis_id: uuid.UUID, brand_id: uuid.UUID
    ) -> tuple[set[str], set[str]]:
        """Every (content_hash, url_hash) already stored for this analysis and brand."""
        statement = select(ContentItemRow.content_hash, ContentItemRow.url_hash).where(
            ContentItemRow.analysis_id == analysis_id,
            ContentItemRow.brand_id == brand_id,
        )
        with Session(self._engine) as session:
            rows = session.execute(statement).all()
        return {r.content_hash for r in rows}, {r.url_hash for r in rows}
