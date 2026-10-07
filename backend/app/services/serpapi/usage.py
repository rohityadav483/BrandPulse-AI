"""Monthly SerpApi counter, reserve guard and live-call kill switch.

docs/DATABASE.md section 5.15: one `serp_usage` row per request attempt; the monthly counter is
`sum(credits)` for the current calendar month (UTC) and the current `SERPAPI_ACCOUNT_LABEL`.
Switching to a new account (new key + new label) therefore starts a clean count.

Pure logic over an injected `UsageStore`; the DB-backed store is
`db/repositories/serp_usage.py`, wired by `pipeline/`.
"""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

from app.schemas.serp import QuotaSnapshot, UsagePurpose, UsageRecord
from app.services.serpapi.cache import utcnow


class LiveDataDisabled(Exception):
    """`ALLOW_LIVE_SERPAPI` is off, so no network call may be made (API: live_data_disabled)."""


class QuotaLow(Exception):
    """A live call would leave fewer than `reserve` searches this month (API: serpapi_quota_low)."""

    def __init__(self, remaining: int, reserve: int) -> None:
        super().__init__(f"{remaining} searches left this month; reserve is {reserve}")
        self.remaining = remaining
        self.reserve = reserve


class UsageStore(Protocol):
    """Storage port. Implemented by `SerpUsageRepository` and `InMemoryUsageStore`."""

    def monthly_credits(
        self, account_label: str, start: datetime, end: datetime
    ) -> int: ...

    def add(self, record: UsageRecord) -> None: ...


def month_bounds(moment: datetime) -> tuple[datetime, datetime]:
    """[start, next start) of the UTC calendar month containing `moment`."""
    moment = moment.astimezone(UTC)
    start = moment.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if start.month == 12:
        end = start.replace(year=start.year + 1, month=1)
    else:
        end = start.replace(month=start.month + 1)
    return start, end


def month_label(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y-%m")


class MonthlyQuota:
    def __init__(
        self,
        store: UsageStore,
        *,
        account_label: str,
        limit: int,
        reserve: int,
        allow_live: bool,
        clock: Callable[[], datetime] = utcnow,
    ) -> None:
        if reserve > limit:
            raise ValueError("reserve must not exceed limit")
        self._store = store
        self._label = account_label
        self._limit = limit
        self._reserve = reserve
        self._allow_live = allow_live
        self._clock = clock

    @property
    def account_label(self) -> str:
        return self._label

    @property
    def live_enabled(self) -> bool:
        return self._allow_live

    def snapshot(self) -> QuotaSnapshot:
        now = self._clock()
        start, end = month_bounds(now)
        used = self._store.monthly_credits(self._label, start, end)
        return QuotaSnapshot(
            month=month_label(now),
            limit=self._limit,
            used=used,
            remaining=max(0, self._limit - used),
            reserve=self._reserve,
            live_enabled=self._allow_live,
        )

    def check_live(self, calls: int = 1) -> None:
        """Raise unless `calls` more live searches are allowed right now.

        Order matters: the kill switch is checked first so a disabled switch never reaches the
        usage store, let alone the network.
        """
        if not self._allow_live:
            raise LiveDataDisabled(
                "live SerpApi calls are disabled (ALLOW_LIVE_SERPAPI=false)"
            )
        remaining = self.snapshot().remaining
        if remaining - calls < self._reserve:
            raise QuotaLow(remaining, self._reserve)

    def record(
        self,
        *,
        cache_key: str,
        engine: str,
        cache_hit: bool,
        credits: int,
        purpose: UsagePurpose,
        http_status: int | None = None,
        analysis_id: UUID | None = None,
        investigation_id: UUID | None = None,
    ) -> UsageRecord:
        """Log one request attempt. Cache hits and failed calls carry `credits=0`."""
        record = UsageRecord(
            cache_key=cache_key,
            engine=engine,
            cache_hit=cache_hit,
            credits=credits,
            http_status=http_status,
            analysis_id=analysis_id,
            investigation_id=investigation_id,
            purpose=purpose,
            account_label=self._label,
            created_at=self._clock(),
        )
        self._store.add(record)
        return record
