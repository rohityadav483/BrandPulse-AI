"""`serp_cache` access. Implements `services.serpapi.cache.CacheStore`.

Each call runs in its own short transaction on its own session, so a cached response (and the
credit it cost) is durable immediately, independent of the pipeline's per-stage transactions.
Only `pipeline/` constructs and wires this class.
"""

from datetime import datetime

from sqlalchemy import delete, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.db.models.serp import SerpCache
from app.schemas.serp import CacheEntry


class SerpCacheRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def get(self, cache_key: str) -> CacheEntry | None:
        with Session(self._engine) as session:
            row = session.get(SerpCache, cache_key)
            if row is None:
                return None
            return CacheEntry(
                cache_key=row.cache_key,
                engine=row.engine,
                params=row.params,
                response=row.response,
                http_status=row.http_status,
                fetched_at=row.fetched_at,
                expires_at=row.expires_at,
                pinned=row.pinned,
            )

    def put(self, entry: CacheEntry) -> None:
        """Insert, or replace the existing row for the same key (a refresh)."""
        values = {
            "cache_key": entry.cache_key,
            "engine": entry.engine,
            "params": entry.params,
            "response": entry.response,
            "http_status": entry.http_status,
            "fetched_at": entry.fetched_at,
            "expires_at": entry.expires_at,
            "pinned": entry.pinned,
        }
        statement = pg_insert(SerpCache).values(**values)
        statement = statement.on_conflict_do_update(
            index_elements=[SerpCache.cache_key],
            set_={
                name: statement.excluded[name] for name in values if name != "cache_key"
            },
        )
        with Session(self._engine) as session, session.begin():
            session.execute(statement)

    def set_pinned(self, cache_key: str, pinned: bool) -> bool:
        statement = (
            update(SerpCache)
            .where(SerpCache.cache_key == cache_key)
            .values(pinned=pinned)
        )
        with Session(self._engine) as session, session.begin():
            return session.execute(statement).rowcount > 0

    def purge_expired(self, now: datetime) -> int:
        """Delete expired rows. Pinned rows are never purged (DATABASE.md section 8)."""
        statement = delete(SerpCache).where(
            SerpCache.expires_at <= now, SerpCache.pinned.is_(False)
        )
        with Session(self._engine) as session, session.begin():
            return session.execute(statement).rowcount
