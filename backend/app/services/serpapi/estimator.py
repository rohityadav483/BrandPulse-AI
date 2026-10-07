"""Estimate a plan without calling anything: cached vs new calls, quota, whether it can run.

Output mirrors `POST /analyses/estimate` (API.md section 3.11); the pipeline maps it onto
`EstimateAnalysisResponse`. No side effects, no credits, no network. Cache lookups are read-only.
"""

from app.schemas.domain import BlockedReason
from app.schemas.serp import QuotaSnapshot, SerpEstimate, SerpPlan
from app.services.serpapi.cache import ResponseCache


def estimate_plan(
    plan: SerpPlan,
    cache: ResponseCache,
    quota: QuotaSnapshot,
    *,
    access_code_required: bool = False,
    daily_limit_reached: bool = False,
) -> SerpEstimate:
    """Count how many of `plan`'s calls are cached and how many would spend credits.

    `access_code_required` = a `LIVE_ACCESS_CODE` is configured. `daily_limit_reached` comes from
    the pipeline (analyses today >= MAX_ANALYSES_PER_DAY); it is not a SerpApi concept.
    Blocking order: daily limit, then (only if new calls are needed) live switch, then reserve.
    """
    cached = []
    new = []
    for call in plan.calls:
        (cached if cache.contains(call.spec) else new).append(call)

    blocked: BlockedReason | None = None
    if daily_limit_reached:
        blocked = BlockedReason.daily_limit_reached
    elif new and not quota.live_enabled:
        blocked = BlockedReason.live_data_disabled
    elif new and quota.remaining - len(new) < quota.reserve:
        blocked = BlockedReason.serpapi_quota_low

    return SerpEstimate(
        windows=plan.windows,
        planned_calls=plan.planned_calls,
        cached_calls=len(cached),
        estimated_new_calls=len(new),
        quota=quota,
        live_enabled=quota.live_enabled,
        needs_access_code=access_code_required and bool(new),
        can_run=blocked is None,
        blocked_reason=blocked,
        new_calls=new,
        cached=cached,
    )
