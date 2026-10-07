"""Record sanitized SerpApi responses as test fixtures.

SAFE BY DEFAULT: with no flags this only prints the plan and makes no network call and no DB
connection. A live recording spends real SerpApi credits and needs ALL of:

  - `--live`
  - `--confirm-credits N`, where N equals the number of planned calls (an upper bound on spend)
  - ALLOW_LIVE_SERPAPI=true, SERPAPI_API_KEY and DATABASE_URL in the environment / .env

Every live call goes through the normal cache, reserve and usage machinery with purpose
`fixture_recording`, so recorded credits show up in the monthly counter and cached calls are
free. Responses are sanitized (no API key) before being written to tests/fixtures/serpapi/.

Usage (from backend/):
    python scripts/record_serp_fixtures.py --brand Samsung --product "Galaxy S25 Ultra" \\
        --competitor Apple --as-of 2026-08-10
    python scripts/record_serp_fixtures.py ... --live --confirm-credits 9
"""

import argparse
import json
import re
import sys
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from app.services.serpapi.query_planner import build_plan
from app.services.serpapi.sanitize import sanitize_response

DEFAULT_OUT = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "serpapi"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--brand", required=True)
    parser.add_argument("--product", default=None)
    parser.add_argument("--competitor", action="append", default=[], dest="competitors")
    parser.add_argument("--as-of", required=True, help="YYYY-MM-DD")
    parser.add_argument("--period", type=int, default=30, choices=[7, 14, 30])
    parser.add_argument("--max-calls", type=int, default=12)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--live", action="store_true", help="spend real credits")
    parser.add_argument("--confirm-credits", type=int, default=None)
    return parser


def fixture_name(index: int, label: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", label.casefold()).strip("_")
    return f"recorded_{index:02d}_{slug}.json"


def wrap_recording(call_label: str, params: dict[str, Any], response: dict[str, Any]) -> dict:
    return {
        "_fixture": {
            "kind": "recorded",
            "label": call_label,
            "recorded_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "params": params,
        },
        **sanitize_response(response),
    }


def _load_settings() -> Any:
    from app.config.settings import get_settings

    return get_settings()


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    plan = build_plan(
        brand=args.brand,
        product=args.product,
        competitors=args.competitors,
        as_of_date=date.fromisoformat(args.as_of),
        period_days=args.period,
        max_calls=args.max_calls,
    )
    print(f"Plan: {plan.planned_calls} call(s) (upper bound; cached calls cost nothing)")
    for index, call in enumerate(plan.calls, start=1):
        print(f"  {index:02d} {call.label}  q={call.spec.query!r}")
    if not args.live:
        print("Plan only: no network call, no database connection, no credits spent.")
        return 0
    if args.confirm_credits != plan.planned_calls:
        print(f"Refusing: pass --confirm-credits {plan.planned_calls} to approve the spend.")
        return 2
    return _run_live(args, plan)


def _run_live(args: argparse.Namespace, plan: Any) -> int:
    settings = _load_settings()
    if not settings.allow_live_serpapi:
        print("Refusing: ALLOW_LIVE_SERPAPI is not true.")
        return 2
    if not settings.serpapi_configured:
        print("Refusing: SERPAPI_API_KEY is not set.")
        return 2
    if not settings.database_url:
        print("Refusing: DATABASE_URL is required so credits are counted.")
        return 2

    from app.db.repositories.serp_cache import SerpCacheRepository
    from app.db.repositories.serp_usage import SerpUsageRepository
    from app.db.session import get_engine
    from app.schemas.serp import UsagePurpose
    from app.services.serpapi.budget import RunBudget
    from app.services.serpapi.cache import ResponseCache
    from app.services.serpapi.client import SerpApiClient
    from app.services.serpapi.fetcher import SerpFetcher
    from app.services.serpapi.usage import MonthlyQuota

    engine = get_engine(settings.database_url)
    cache = ResponseCache(SerpCacheRepository(engine), ttl_hours=settings.serp_cache_ttl_hours)
    quota = MonthlyQuota(
        SerpUsageRepository(engine),
        account_label=settings.serpapi_account_label,
        limit=settings.serp_monthly_limit,
        reserve=settings.serp_monthly_reserve,
        allow_live=settings.allow_live_serpapi,
    )
    client = SerpApiClient(
        api_key=settings.serpapi_api_key.get_secret_value(),
        allow_live=settings.allow_live_serpapi,
    )
    fetcher = SerpFetcher(cache=cache, quota=quota, client=client)
    result = fetcher.collect(
        plan,
        budget=RunBudget(settings.serp_budget_per_analysis),
        purpose=UsagePurpose.fixture_recording,
    )

    args.out.mkdir(parents=True, exist_ok=True)
    for index, (call, fetched) in enumerate(result.fetched, start=1):
        body = wrap_recording(call.label, dict(call.spec.params), fetched.response)
        path = args.out / fixture_name(index, call.label)
        path.write_text(json.dumps(body, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"wrote {path.name} ({fetched.source.value})")
    for warning in result.warnings:
        print(f"warning [{warning.code}]: {warning.message}")
    print(f"Spent {result.live_calls} credit(s); {result.cache_hits} served from cache.")
    return 0 if result.complete else 1


if __name__ == "__main__":
    sys.exit(main())
