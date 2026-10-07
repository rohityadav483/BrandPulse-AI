"""Persistent SerpApi response cache (replaces Redis). docs/DATABASE.md section 5.4.

Pure logic over an injected `CacheStore`; the DB-backed store is
`db/repositories/serp_cache.py`, wired by `pipeline/`.

Rules:
- Key = sha256 of engine + normalised params. Dates must be absolute so a replay on another day
  hits the same entry. The API key is never part of the key and never stored.
- Only successful (2xx) responses are stored. A "no results" response is stored with a shorter
  TTL; any other SerpApi error payload is refused.
- Pinned rows (demo entries) never expire and are never purged.
"""

import hashlib
import json
import re
from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from app.schemas.serp import CacheEntry, ParamValue, QuerySpec
from app.services.serpapi.parsers.common import (
    has_results,
    is_no_results_error,
    response_error,
)
from app.services.serpapi.sanitize import sanitize_response

# Empty results are cached briefly: the query may start returning data soon.
EMPTY_RESULT_TTL_HOURS = 24

# Params that do not change response content, so they must not split the cache.
_IGNORED_PARAMS = frozenset({"api_key", "no_cache", "async"})
# SerpApi queries are case-insensitive for our purposes; folding avoids paying twice.
_CASEFOLDED_PARAMS = frozenset({"q", "search_query"})

_RELATIVE_TRENDS_DATE = re.compile(r"^(now|today)\b", re.IGNORECASE)
_RELATIVE_NEWS_OPERATOR = re.compile(r"\bwhen:\s*\d", re.IGNORECASE)


class RelativeDateError(ValueError):
    """A request used a relative date, which would make cache keys drift day by day."""


class CacheStore(Protocol):
    """Storage port. Implemented by `SerpCacheRepository` and `InMemoryCacheStore`."""

    def get(self, cache_key: str) -> CacheEntry | None: ...

    def put(self, entry: CacheEntry) -> None: ...

    def set_pinned(self, cache_key: str, pinned: bool) -> bool: ...

    def purge_expired(self, now: datetime) -> int: ...


def utcnow() -> datetime:
    return datetime.now(UTC)


def normalize_params(params: Mapping[str, ParamValue]) -> dict[str, str]:
    """Stable string form of request params (ignored params dropped, queries case-folded)."""
    normalized: dict[str, str] = {}
    for key, value in params.items():
        if key in _IGNORED_PARAMS or value is None:
            continue
        if isinstance(value, bool):
            text = "true" if value else "false"
        else:
            text = " ".join(str(value).split())
        normalized[key] = text.casefold() if key in _CASEFOLDED_PARAMS else text
    return normalized


def cache_key(engine: str, params: Mapping[str, ParamValue]) -> str:
    payload = json.dumps(
        {"engine": str(engine), "params": normalize_params(params)},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def assert_absolute_dates(spec: QuerySpec) -> None:
    """Refuse relative date filters (`tbs=qdr:*`, Trends `today 1-m`, News `when:7d`)."""
    params = spec.params
    if "qdr:" in str(params.get("tbs", "")).casefold():
        raise RelativeDateError(
            "relative date filter in `tbs`; use absolute `cdr:` dates"
        )
    if _RELATIVE_TRENDS_DATE.match(str(params.get("date", "")).strip()):
        raise RelativeDateError("relative Trends `date`; use two absolute dates")
    if _RELATIVE_NEWS_OPERATOR.search(str(params.get("q", ""))):
        raise RelativeDateError(
            "relative `when:` operator in query; use after:/before:"
        )


def is_fresh(entry: CacheEntry, now: datetime) -> bool:
    return entry.pinned or entry.expires_at > now


class ResponseCache:
    def __init__(
        self,
        store: CacheStore,
        *,
        ttl_hours: int,
        empty_ttl_hours: int = EMPTY_RESULT_TTL_HOURS,
        clock: Callable[[], datetime] = utcnow,
    ) -> None:
        self._store = store
        self._ttl = timedelta(hours=ttl_hours)
        self._empty_ttl = timedelta(hours=min(empty_ttl_hours, ttl_hours))
        self._clock = clock

    @staticmethod
    def key_for(spec: QuerySpec) -> str:
        return cache_key(spec.engine, spec.params)

    def lookup(self, spec: QuerySpec) -> CacheEntry | None:
        """The fresh entry for `spec`, or None on a miss or an expired (unpinned) entry."""
        entry = self._store.get(self.key_for(spec))
        if entry is None or not is_fresh(entry, self._clock()):
            return None
        return entry

    def contains(self, spec: QuerySpec) -> bool:
        """Side-effect-free hit check, used by the estimator."""
        return self.lookup(spec) is not None

    def store(
        self,
        spec: QuerySpec,
        response: Mapping[str, Any],
        *,
        http_status: int = 200,
    ) -> CacheEntry:
        """Cache a successful response. Raises ValueError for non-2xx or error payloads."""
        if not 200 <= http_status < 300:
            raise ValueError(f"only 2xx responses are cached (got {http_status})")
        error = response_error(response)
        if error is not None and not is_no_results_error(error):
            raise ValueError("SerpApi error responses are not cached")

        key = self.key_for(spec)
        now = self._clock()
        empty = not has_results(spec.engine, response)
        existing = self._store.get(key)
        entry = CacheEntry(
            cache_key=key,
            engine=str(spec.engine),
            params=dict(spec.params),
            response=sanitize_response(dict(response)),
            http_status=http_status,
            fetched_at=now,
            expires_at=now + (self._empty_ttl if empty else self._ttl),
            pinned=bool(
                existing and existing.pinned
            ),  # a refresh never unpins demo data
        )
        self._store.put(entry)
        return entry

    def pin(self, spec: QuerySpec) -> bool:
        """Mark an entry as a demo entry (never expires, never purged). False if absent."""
        return self._store.set_pinned(self.key_for(spec), True)

    def unpin(self, spec: QuerySpec) -> bool:
        return self._store.set_pinned(self.key_for(spec), False)

    def purge_expired(self) -> int:
        """Delete expired, unpinned rows. Returns how many were removed."""
        return self._store.purge_expired(self._clock())
