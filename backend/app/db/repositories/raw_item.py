"""`raw_items` access: create, retrieve and check persisted RawItems (Phase 3.1).

No normalisation or deduplication happens here (Phase 3.2). The only guarantee is idempotency:
the unique index on (analysis, brand, purpose, raw_key) turns a re-persist of the same parsed
response into a no-op, reported as `duplicates`.

Like the SerpApi repositories this takes an `Engine` and runs each call in one short
transaction on its own session, so a batch is all-or-nothing. Only `pipeline/` constructs and
wires this class.
"""

import uuid
from collections.abc import Iterable, Sequence

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from sqlalchemy.sql import Select

from app.db.models.raw_item import RawItemRow
from app.schemas.domain import ContentPurpose, SourceType, WindowKind
from app.schemas.serp import RawItem, RawItemContext, RawItemWriteResult, StoredRawItem

_IDENTITY = [
    RawItemRow.analysis_id,
    RawItemRow.brand_id,
    RawItemRow.purpose,
    RawItemRow.raw_key,
]


def _values(context: RawItemContext, item: RawItem) -> dict:
    values: dict = {
        "analysis_id": context.analysis_id,
        "brand_id": context.brand_id,
        "purpose": context.purpose,
        "window": context.window,
        "source_type": item.source_type,
        "engine": item.engine.value,
        "title": item.title,
        "url": item.url,
        "snippet": item.snippet,
        "author": item.author,
        "published_raw": item.published_raw,
        "published_iso": item.published_iso,
        "position": item.position,
        "query": item.query,
        "serp_cache_key": item.serp_cache_key,
        "item_metadata": item.metadata,
        "raw_key": item.compute_raw_key(),
    }
    if context.collected_at is not None:  # else the column default (now()) applies
        values["collected_at"] = context.collected_at
    return values


def _to_stored(row: RawItemRow) -> StoredRawItem:
    return StoredRawItem(
        id=row.id,
        analysis_id=row.analysis_id,
        brand_id=row.brand_id,
        purpose=row.purpose,
        window=row.window,
        source_type=row.source_type,
        engine=row.engine,
        title=row.title,
        url=row.url,
        snippet=row.snippet,
        author=row.author,
        published_raw=row.published_raw,
        published_iso=row.published_iso,
        position=row.position,
        query=row.query,
        serp_cache_key=row.serp_cache_key,
        metadata=row.item_metadata,
        raw_key=row.raw_key,
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
    statement = statement.where(RawItemRow.analysis_id == analysis_id)
    if brand_id is not None:
        statement = statement.where(RawItemRow.brand_id == brand_id)
    if purpose is not None:
        statement = statement.where(RawItemRow.purpose == purpose)
    if window is not None:
        statement = statement.where(RawItemRow.window == window)
    if source_type is not None:
        statement = statement.where(RawItemRow.source_type == source_type)
    return statement


class RawItemRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    # ---- create ----

    def add_many(
        self, context: RawItemContext, items: Sequence[RawItem]
    ) -> RawItemWriteResult:
        """Persist a batch in one transaction. Exact repeats are skipped, never updated.

        Repeats include items already stored and identical items inside this batch.
        """
        if not items:
            return RawItemWriteResult(inserted=0, duplicates=0)
        statement = (
            pg_insert(RawItemRow)
            .values([_values(context, item) for item in items])
            .on_conflict_do_nothing(index_elements=_IDENTITY)
            .returning(RawItemRow.id)
        )
        with Session(self._engine) as session, session.begin():
            inserted_ids = list(session.execute(statement).scalars())
        return RawItemWriteResult(
            inserted=len(inserted_ids),
            duplicates=len(items) - len(inserted_ids),
            inserted_ids=inserted_ids,
        )

    def add(self, context: RawItemContext, item: RawItem) -> tuple[StoredRawItem, bool]:
        """Persist one item. Returns (stored row, created); `created` is False for a repeat."""
        statement = (
            pg_insert(RawItemRow)
            .values(**_values(context, item))
            .on_conflict_do_nothing(index_elements=_IDENTITY)
            .returning(RawItemRow.id)
        )
        with Session(self._engine) as session, session.begin():
            new_id = session.execute(statement).scalar_one_or_none()
            if new_id is not None:
                return _to_stored(session.get_one(RawItemRow, new_id)), True
            existing = session.execute(
                select(RawItemRow).where(
                    RawItemRow.analysis_id == context.analysis_id,
                    RawItemRow.brand_id == context.brand_id,
                    RawItemRow.purpose == context.purpose,
                    RawItemRow.raw_key == item.compute_raw_key(),
                )
            ).scalar_one()
            return _to_stored(existing), False

    # ---- retrieve ----

    def get(self, raw_item_id: uuid.UUID) -> StoredRawItem | None:
        with Session(self._engine) as session:
            row = session.get(RawItemRow, raw_item_id)
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
    ) -> list[StoredRawItem]:
        """Items of an analysis, optionally filtered. Stable order: collected_at, engine,
        position (nulls last), id."""
        statement = _filtered(
            select(RawItemRow), analysis_id, brand_id, purpose, window, source_type
        ).order_by(
            RawItemRow.collected_at,
            RawItemRow.engine,
            RawItemRow.position.asc().nulls_last(),
            RawItemRow.id,
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
            select(func.count()).select_from(RawItemRow),
            analysis_id,
            brand_id,
            purpose,
            window,
            source_type,
        )
        with Session(self._engine) as session:
            return session.execute(statement).scalar_one()

    # ---- check ----

    def exists(self, context: RawItemContext, item: RawItem) -> bool:
        """True if this exact occurrence is already stored for the context's
        analysis, brand and purpose."""
        return item.compute_raw_key() in self.existing_keys(
            context.analysis_id,
            context.brand_id,
            context.purpose,
            [item.compute_raw_key()],
        )

    def existing_keys(
        self,
        analysis_id: uuid.UUID,
        brand_id: uuid.UUID,
        purpose: ContentPurpose,
        raw_keys: Iterable[str],
    ) -> set[str]:
        """The subset of `raw_keys` already stored (one query; empty input = no query)."""
        wanted = set(raw_keys)
        if not wanted:
            return set()
        statement = select(RawItemRow.raw_key).where(
            RawItemRow.analysis_id == analysis_id,
            RawItemRow.brand_id == brand_id,
            RawItemRow.purpose == purpose,
            RawItemRow.raw_key.in_(wanted),
        )
        with Session(self._engine) as session:
            return set(session.execute(statement).scalars())
