"""Test doubles for the SerpApi layer: in-memory stores, a scripted transport, a network block.

Shipped in the app package (not under `tests/`) because Phase 6 end-to-end tests and the
no-database demo mode (Phase 10) need the same fakes. Nothing here is used on the live path.
"""

import socket
from collections.abc import Callable, Mapping
from datetime import datetime
from typing import Any

from app.schemas.serp import CacheEntry, UsageRecord
from app.services.serpapi.client import TransportResponse


class InMemoryCacheStore:
    """`CacheStore` backed by a dict."""

    def __init__(self) -> None:
        self.rows: dict[str, CacheEntry] = {}

    def get(self, cache_key: str) -> CacheEntry | None:
        return self.rows.get(cache_key)

    def put(self, entry: CacheEntry) -> None:
        self.rows[entry.cache_key] = entry

    def set_pinned(self, cache_key: str, pinned: bool) -> bool:
        entry = self.rows.get(cache_key)
        if entry is None:
            return False
        self.rows[cache_key] = entry.model_copy(update={"pinned": pinned})
        return True

    def purge_expired(self, now: datetime) -> int:
        stale = [key for key, e in self.rows.items() if not e.pinned and e.expires_at <= now]
        for key in stale:
            del self.rows[key]
        return len(stale)


class InMemoryUsageStore:
    """`UsageStore` backed by a list."""

    def __init__(self) -> None:
        self.records: list[UsageRecord] = []

    def monthly_credits(self, account_label: str, start: datetime, end: datetime) -> int:
        return sum(
            r.credits
            for r in self.records
            if r.account_label == account_label and start <= r.created_at < end
        )

    def add(self, record: UsageRecord) -> None:
        self.records.append(record)


Script = Callable[[str, Mapping[str, str]], TransportResponse | Exception]


class ScriptedTransport:
    """`SerpTransport` that answers from a script and records every call (params include the
    key, so assert on `engine`/`q`, never print `calls`)."""

    def __init__(self, script: Script) -> None:
        self._script = script
        self.calls: list[dict[str, str]] = []

    def get(self, url: str, params: Mapping[str, str], timeout: float) -> TransportResponse:
        self.calls.append(dict(params))
        outcome = self._script(params["engine"], params)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def ok(body: Mapping[str, Any], status: int = 200) -> TransportResponse:
    return TransportResponse(status, dict(body))


def block_network(monkeypatch: Any) -> None:
    """Make any socket connection or DNS lookup raise, so a test cannot reach SerpApi."""

    def _blocked(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("network access is blocked in SerpApi tests")

    monkeypatch.setattr(socket.socket, "connect", _blocked)
    monkeypatch.setattr(socket, "create_connection", _blocked)
    monkeypatch.setattr(socket, "getaddrinfo", _blocked)
