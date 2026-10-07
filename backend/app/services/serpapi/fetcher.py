"""Run a plan through cache -> guards -> client, logging every attempt.

This is the only place the pieces meet. For each call:

1. fresh cache hit  -> served, usage row `cache_hit=True, credits=0`, no network
2. miss             -> `MonthlyQuota.check_live` (kill switch, then reserve), then `RunBudget.check`
3. client call      -> success: cached + usage row `credits=1`; failure: usage row `credits=0`

`collect` never raises for budget, quota, kill-switch or engine failures: it stops spending,
keeps serving cache hits, and returns warnings (codes from API.md section 2) so the pipeline can
finish `partial` with what exists. Pure orchestration over injected ports; no DB, no settings.
"""

import enum
import logging
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from app.schemas.serp import PlannedCall, QuerySpec, SerpPlan, UsagePurpose
from app.services.serpapi.budget import RunBudget, RunBudgetExhausted
from app.services.serpapi.cache import ResponseCache, assert_absolute_dates
from app.services.serpapi.client import (
    SerpApiAccountQuotaExhausted,
    SerpApiAuthError,
    SerpApiClient,
    SerpApiClientError,
    SerpApiLiveDisabled,
    SerpApiNotConfigured,
)
from app.services.serpapi.usage import LiveDataDisabled, MonthlyQuota, QuotaLow

logger = logging.getLogger(__name__)

# Errors after which every further live call would fail the same way: stop calling.
_STOP_LIVE_ERRORS = (
    SerpApiAuthError,
    SerpApiAccountQuotaExhausted,
    SerpApiLiveDisabled,
    SerpApiNotConfigured,
)


class FetchSource(enum.StrEnum):
    cache = "cache"
    live = "live"


class LiveCallsStopped(Exception):
    """Internal: a miss reached the network gate after live calls were stopped for this run."""


@dataclass(frozen=True)
class FetchResult:
    spec: QuerySpec
    cache_key: str
    response: dict[str, Any]
    source: FetchSource
    credits: int
    http_status: int | None

    @property
    def cache_hit(self) -> bool:
        return self.source is FetchSource.cache


@dataclass(frozen=True)
class CollectionWarning:
    """Mapped by the pipeline onto `Warning(code, message, stage="collecting")`."""

    code: str
    message: str


@dataclass
class CollectionResult:
    fetched: list[tuple[PlannedCall, FetchResult]] = field(default_factory=list)
    skipped: list[tuple[PlannedCall, str]] = field(default_factory=list)  # (call, reason code)
    warnings: list[CollectionWarning] = field(default_factory=list)

    @property
    def live_calls(self) -> int:
        return sum(result.credits for _, result in self.fetched)

    @property
    def cache_hits(self) -> int:
        return sum(1 for _, result in self.fetched if result.cache_hit)

    @property
    def complete(self) -> bool:
        return not self.skipped


class SerpFetcher:
    def __init__(
        self,
        *,
        cache: ResponseCache,
        quota: MonthlyQuota,
        client: SerpApiClient,
    ) -> None:
        self._cache = cache
        self._quota = quota
        self._client = client

    def fetch(
        self,
        spec: QuerySpec,
        *,
        budget: RunBudget,
        purpose: UsagePurpose,
        analysis_id: UUID | None = None,
        investigation_id: UUID | None = None,
        network: bool = True,
    ) -> FetchResult:
        """One request. May raise LiveDataDisabled, QuotaLow, RunBudgetExhausted or a
        `SerpApiClientError`; a cache hit never raises and never touches the network."""
        assert_absolute_dates(spec)
        key = self._cache.key_for(spec)
        context = {
            "purpose": purpose,
            "analysis_id": analysis_id,
            "investigation_id": investigation_id,
        }

        entry = self._cache.lookup(spec)
        if entry is not None:
            self._quota.record(
                cache_key=key,
                engine=str(spec.engine),
                cache_hit=True,
                credits=0,
                http_status=entry.http_status,
                **context,
            )
            return FetchResult(spec, key, entry.response, FetchSource.cache, 0, entry.http_status)

        if not network:
            raise LiveCallsStopped
        self._quota.check_live()  # kill switch first, then the monthly reserve
        budget.check()

        try:
            result = self._client.fetch(spec)
        except SerpApiClientError as exc:
            self._quota.record(
                cache_key=key,
                engine=str(spec.engine),
                cache_hit=False,
                credits=0,
                http_status=exc.http_status,
                **context,
            )
            raise

        try:
            self._cache.store(spec, result.response, http_status=result.http_status)
        finally:
            # The credit was spent whether or not caching worked, so always count it.
            self._quota.record(
                cache_key=key,
                engine=str(spec.engine),
                cache_hit=False,
                credits=1,
                http_status=result.http_status,
                **context,
            )
            budget.consume(1)
        return FetchResult(spec, key, result.response, FetchSource.live, 1, result.http_status)

    def collect(
        self,
        plan: SerpPlan,
        *,
        budget: RunBudget,
        purpose: UsagePurpose,
        analysis_id: UUID | None = None,
        investigation_id: UUID | None = None,
    ) -> CollectionResult:
        """Fetch every call in plan order. Never raises for guard or engine failures."""
        out = CollectionResult()
        warned: set[str] = set()
        network = True

        def warn(code: str, message: str, *, once: bool = True) -> None:
            if once and code in warned:
                return
            warned.add(code)
            out.warnings.append(CollectionWarning(code, message))

        for call in plan.calls:
            try:
                result = self.fetch(
                    call.spec,
                    budget=budget,
                    purpose=purpose,
                    analysis_id=analysis_id,
                    investigation_id=investigation_id,
                    network=network,
                )
            except LiveDataDisabled:
                warn("live_data_disabled", "Live SerpApi calls are off; using cached data only.")
                out.skipped.append((call, "live_data_disabled"))
            except QuotaLow as exc:
                warn(
                    "serpapi_budget_exhausted",
                    f"Monthly SerpApi reserve reached ({exc.remaining} left, {exc.reserve} held).",
                )
                out.skipped.append((call, "serpapi_quota_low"))
            except RunBudgetExhausted as exc:
                warn(
                    "serpapi_budget_exhausted",
                    f"This run's budget of {exc.cap} live searches is used up.",
                )
                out.skipped.append((call, "serpapi_budget_exhausted"))
            except LiveCallsStopped:
                out.skipped.append((call, "live_calls_stopped"))
            except SerpApiClientError as exc:
                logger.warning(
                    "serpapi_call_failed",
                    extra={"engine": str(call.spec.engine), "code": exc.code},
                )
                warn(
                    "serpapi_engine_failed",
                    f"{call.spec.engine} returned no usable results ({exc.code}).",
                    once=False,
                )
                out.skipped.append((call, exc.code))
                if isinstance(exc, _STOP_LIVE_ERRORS):
                    network = False
            else:
                out.fetched.append((call, result))
        return out
