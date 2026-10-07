# serpapi

Budgeted, cached SerpApi collection (docs/ARCHITECTURE.md section 6). Pure logic: no FastAPI, no
SQLAlchemy, no settings. Stores and the transport are injected; `pipeline/` wires them.

## Inputs and outputs

| Module | In | Out |
|---|---|---|
| `query_planner.build_plan` | brand, product, competitors, `as_of_date`, period, call cap | `SerpPlan` (ordered `PlannedCall`s, `dropped` tail) |
| `cache.ResponseCache` | `QuerySpec` (+ response to store) | `CacheEntry` or miss; pin/unpin/purge |
| `usage.MonthlyQuota` | usage store, account label, limit, reserve, live flag | `QuotaSnapshot`; raises `LiveDataDisabled` / `QuotaLow` |
| `budget.RunBudget` | per-run cap | raises `RunBudgetExhausted` |
| `client.SerpApiClient` | `QuerySpec` | `ClientResult` or a `SerpApiClientError` subclass |
| `estimator.estimate_plan` | plan, cache, quota snapshot | `SerpEstimate` (cached / new calls, `can_run`, `blocked_reason`) |
| `fetcher.SerpFetcher` | plan + `RunBudget` | `CollectionResult` (fetched, skipped, warnings) |
| `parsers.parse_response` | `QuerySpec` + raw JSON | `ParsedResponse` (`RawItem[]`, or `TrendSeries` for Trends) |

Shared types live in `app/schemas/serp.py`. Storage ports (`CacheStore`, `UsageStore`) are
implemented by `db/repositories/serp_cache.py` and `serp_usage.py`; `testing.py` has in-memory
versions, a scripted transport and `block_network`.

## Rules

- Live switch: `ALLOW_LIVE_SERPAPI=false` by default. The quota guard and the client both refuse,
  so nothing reaches the network. Cache hits still work with the switch off.
- Order on a cache miss: kill switch, monthly reserve (`remaining - 1 >= reserve`), per-run cap,
  then the call.
- Credits: 1 per successful live call, 0 for cache hits and failed calls. One `serp_usage` row per
  attempt. `analyses.serp_calls_used` counts live calls only.
- Cache key: sha256 of engine + normalised params; queries case-folded; API key never included;
  relative dates are refused (`RelativeDateError`). Only 2xx responses are cached; "no results"
  gets a 24 h TTL; pinned rows never expire.
- API key never appears in the cache, usage rows, exceptions, `repr` or logs.
- Failure behaviour: `collect` never raises for guards or engine errors. It returns warnings
  (`live_data_disabled`, `serpapi_budget_exhausted`, `serpapi_engine_failed`), keeps serving cache
  hits and stops calling after an auth, missing-key or account-exhausted error.
- The default transport uses the standard library (`urllib`); no new dependency. Retries: up to 2
  on timeout, network error, 429 (rate limit) and 5xx, with backoff capped at 30 s.

## Tests

`pytest tests/unit/test_serp_*.py tests/parsers tests/unit/test_record_serp_fixtures.py`. Each
module blocks sockets, so a test that tried to go live would fail.
