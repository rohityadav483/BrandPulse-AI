# SerpApi Findings

**Status (Phase 2): no live SerpApi call has been made.** The Phase 2 prompt forbids live calls
during development and tests, so everything below is either built from SerpApi's documented
behaviour or marked **UNVERIFIED**. The first approved live session (a small probe, see
`docs/DEVELOPMENT_PLAN.md` Phase 2) must confirm or correct each UNVERIFIED line and record the
result here.

## What is implemented (no credits spent)

- Persistent cache (`serp_cache`), usage ledger (`serp_usage`), monthly counter with reserve, per-run
  cap, kill switch (`ALLOW_LIVE_SERPAPI=false` by default), estimator, planner, five parsers.
- Fixtures in `backend/tests/fixtures/serpapi/` are **synthetic mocks**, hand-written to the
  documented response shapes and marked `"_fixture": {"kind": "synthetic_mock"}`. They use
  `example.test` URLs. They are not recordings.
- `backend/scripts/record_serp_fixtures.py` records real, sanitized fixtures. It is plan-only
  unless `--live --confirm-credits N` is passed with the env switch on.

## Accounting rules chosen (conservative)

| Situation | Credits logged | Cached |
|---|---|---|
| Live call, HTTP 2xx with results | 1 | yes, normal TTL |
| Live call, HTTP 2xx, "hasn't returned any results" | 1 | yes, 24 h TTL |
| Live call fails (4xx/5xx/timeout/bad body) | 0 | no |
| Cache hit | 0 (row logged with `cache_hit=true`) | n/a |

Failed calls are logged as 0 credits, as DATABASE.md says. UNVERIFIED: whether SerpApi bills
timeouts or "no results" searches. The "no results" case is counted as 1 on purpose so the local
counter never under-reports spend. The monthly counter uses the UTC calendar month; SerpApi may
reset on the billing date instead. UNVERIFIED.

## Assumptions to verify in the first live session

| # | Question | Built assumption | Where it lives |
|---|---|---|---|
| 1 | Google web date range | `tbs=cdr:1,cd_min:M/D/YYYY,cd_max:M/D/YYYY`, both ends inclusive | `query_planner.web_spec` |
| 2 | Google News date range | `after:YYYY-MM-DD before:YYYY-MM-DD` operators inside `q` (`before` = window end + 1 day). Fallback if ignored: `engine=google` with `tbm=nws` and the `tbs` range | `query_planner.news_spec` |
| 3 | Trends window and batching | `data_type=TIMESERIES`, `date="YYYY-MM-DD YYYY-MM-DD"` (baseline start to as-of), up to 5 comma-separated terms in one call = 1 credit | `query_planner.trends_spec` |
| 4 | Forums and YouTube dates | No date filter; results are "current" only | planner |
| 5 | Results per call | Default page (about 10); `num` is not sent. Pagination is never used | planner |
| 6 | Google Forums result keys | `organic_results`, also accepts `forum_results` / `discussions_and_forums` | `parsers/common.RESULT_LIST_KEYS` |
| 7 | News row shape | `source` is an object (`name`, `authors`) or a string; story clusters nest under `stories` | `parsers/google_news.py` |
| 8 | YouTube row shape | `video_results[]` with `channel.name`, `published_date` (relative), `views` int | `parsers/youtube.py` |
| 9 | Account-exhausted error | HTTP 429 with a message containing "run out of searches" is non-retryable | `client._is_account_exhausted` |
| 10 | Empty search | `error` text containing "returned any results" with HTTP 200 | `parsers/common.is_no_results_error` |
| 11 | Credits per plan | 11 for target + 2 competitors; competitor queries are brand name only | planner |

## Still to do before Phase 3 depends on real data

- Run the approved probe (the Samsung "battery" signal check) and record the answers above.
- Record real fixtures and replace or add to the synthetic ones; keep the synthetic files only if
  they still serve a test.
- Pin the demo cache entries (`ResponseCache.pin`) after the demo analysis is recorded.
