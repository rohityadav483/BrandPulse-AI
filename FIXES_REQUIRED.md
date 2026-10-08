# FIXES_REQUIRED

Review of BrandPulse-AI-main. The original review modified no project files.

## Fix status (2026-10-08, current checkpoint)

The latest checkpoint contains the earlier verified core fixes plus the remaining Task 4/hardening work implemented in this session. PostgreSQL-backed and browser-level verification cannot be completed in this sandbox because `psycopg`/PostgreSQL and frontend npm dependencies are unavailable and outbound package installation is blocked. Do not treat those environment-limited checks as failures.

Current status:
- Core analysis pipeline issues 1-5: **FIXED and VERIFIED** in the prior PostgreSQL session.
- Investigation pipeline issues: **FIXED and VERIFIED** in the prior PostgreSQL session.
- Jobs/reaper/signal API/demo-mode/migration fixes: **FIXED - NOT FULLY VERIFIED**; prior implementation had dedicated tests but this checkpoint could not rerun the PostgreSQL suite.
- LLM audit/limiter, confidence, relevance/trends, `.env.example`: **FIXED - NOT FULLY VERIFIED**; prior full PostgreSQL run was green before the final added tests, but the final database suite could not be reproduced here.
- Frontend live-mode fetch and investigation start/poll flow: **IMPLEMENTED - NOT FULLY VERIFIED**; static/code-level checks and contract checks pass, but npm dependencies are unavailable in this sandbox.
- CI workflow: **IMPLEMENTED - NOT FULLY VERIFIED**; workflow is present but cannot be executed here.
- Demo scripts: **IMPLEMENTED - NOT FULLY VERIFIED**; scripts compile and fail cleanly without a database, but were not executed against PostgreSQL.
- Root test/script duplication: **FIXED**; canonical test/script trees now live under `backend/`.
- No-database investigation routes: **FIXED and VERIFIED** by 26 targeted backend tests in this checkpoint.
- Live access code hardening and early analysis-start error handling: **IMPLEMENTED - NOT FULLY VERIFIED**; code compiles, but database integration verification remains pending.
- Evidence stance/relevance discrepancy: **RESOLVED BY DOCUMENTED MVP SCOPE**; the current investigation path is explicitly cache-safe/deterministic for evidence scoring, with Groq used for synthesis/reasoning where configured.

This checkpoint should be followed by one real-machine verification pass with PostgreSQL and frontend dependencies before declaring the project production-ready.

## Fourth session status (2026-10-08, stopped early at the session limit)

Fixed, new tests pass individually, but the FULL backend suite was NOT re-run after the new tests were added, and ruff / `export_openapi --check` / `validate_golden` / revert-one-fix checks were not run. Treat as FIXED - NOT FULLY VERIFIED:
- `llm_calls` recording and LLM concurrency (new `services/llm/audit.py`, shared `LLMLimiter`, `LLMCall` registered, `include_object` hack and `migration_filters.py` removed, FKs added to models). The full suite (1185 passed / 3 skipped, PostgreSQL 16) was green after these code changes but before the new tests.
- Investigation confidence inputs derived from evidence (`derive_confidence_inputs`).
- Analysis relevance (product in the target profile, stored `is_about_brand`, snapshots count only about-brand items) and Trends (points stored per brand, `interest_change_pct`, `trend_corroborated`, dashboard `search_interest`). Aliases: the brands table has no alias column, so none are passed.
- `backend/.env.example` replaced with every `Settings` field (blank secrets, live and demo off); 3 new tests in `tests/unit/test_settings.py`.

NOT done in this session (still open): frontend live-mode relative URL, frontend start/poll investigation flow, `.github/workflows/ci.yml` (still empty), demo scripts (`seed_demo.py`, `probe_demo_signal.py`, `warm_demo_cache.py` still 0 bytes), stale root `tests/` and `scripts/` (still present; `check_type_contract.py` exists only at the root).


Third session (2026-10-08): five HIGH items below are **FIXED - NOT YET VERIFIED**. The code and tests were written, but the sandbox had no PostgreSQL, no FastAPI/SQLAlchemy/pytest and no network, so no test, `export_openapi --check` or `ruff` run was possible; only `py_compile` and a static import check were run. Run the verification block under "Third session" before treating them as done.

Fixed and verified: critical issues 1-5 of the core analysis pipeline (first session) and the six Investigation Pipeline issues (second session, 2026-10-08), all marked **FIXED and VERIFIED** below. Everything else in this file is still open and was not touched.

Investigation Pipeline session (PostgreSQL 16, local; `TEST_DATABASE_URL` set):
- Backend with Postgres: 1120 passed / 5 failed / 3 skipped (before this session 1105 / 5 / 3). The same 5 pre-existing migration-test failures remain (HIGH item "Pipelines and routes are untested; migration tests are red with a database"); not part of this fix.
- Backend without Postgres: 887 passed / 241 skipped (before: 876 / 237).
- 15 new tests: 11 unit (`tests/unit/test_investigation_synthesizer.py`) and 4 PostgreSQL integration (`tests/integration/test_investigation_pipeline_e2e.py`). On the original code the 4 integration tests fail (investigation ends `failed` at `generating_queries`) and the unit file cannot import. Each fix was also reverted one at a time in a scratch copy of the fixed code; every revert makes at least one new test fail.
- Full run signal -> evidence -> competitor comparison -> synthesis -> recommendations -> stored report, with Samsung + 2 competitors from a real `run_analysis` (scripted SerpApi, stub sentiment model). `GET /investigations/{id}` returned 200 while queued, after every step transition, when completed and when failed, with only `done`/`active`/`pending` step states. The report is stored in `investigations.report` and read back through the API; recommendation rows match the report.
- Valid evidence IDs are kept in order; findings with invented, mixed, empty or missing IDs are removed; if nothing grounded survives, the deterministic fallback report is used.
- `export_openapi --check` and `validate_golden` pass. Frontend not touched.

Third session - Jobs, Signals, Investigation API, Demo Mode, migration tests (UNVERIFIED, nothing was executed):
- What was written: `pipeline/jobs.py` (waiting gate, reaper, investigation job), `api/v1/signals.py` (contract), demo branches in `analyses.py` / `usage.py`, signal status sync in `investigation_pipeline.py`, `app/db/migration_filters.py` (shared `include_object`), updated `tests/integration/test_migrations.py`, new `tests/unit/test_demo_mode_api.py`, `tests/unit/test_jobs_concurrency.py`, `tests/integration/test_jobs_and_signals_api.py`.
- To verify (PostgreSQL 16, `TEST_DATABASE_URL` set): `cd backend && pytest` (full suite, expect 0 failures apart from the 3 torch skips), `pytest tests/unit` without Postgres, `python scripts/export_openapi.py --check`, `python scripts/validate_golden.py`, `ruff check .`. For each of the five fixes revert it in a scratch copy and confirm a new test fails.
- Known risks to look at first if something is red: ruff import order in the new test files; the drift test (`test_models_match_migrated_schema`) now hides exactly what `alembic/env.py` hides, and if it still reports drift on evidence/investigations/recommendations that is a real model/migration mismatch that was not found by reading; `contracts/openapi.json` should be unchanged (route signatures keep the same parameters and responses).

Verification (PostgreSQL 16, local; `TEST_DATABASE_URL` set):
- Backend with Postgres: 1105 passed / 5 failed / 3 skipped (baseline 1092 / 5 / 3). The 5 failures are the pre-existing migration-test failures from the HIGH item "Pipelines and routes are untested; migration tests are red with a database"; not part of this fix.
- Backend without Postgres: 876 passed / 237 skipped.
- 13 new tests (4 pipeline end-to-end, 3 repository, 6 enum guard). Each fix was reverted in a scratch copy to confirm a new test fails without it; on the original code the end-to-end and repository tests fail with `DetachedInstanceError` and `'Engine' object has no attribute 'add_all'`.
- Full `run_analysis` with target + 2 competitors: status `completed`/`partial`, stage `done`, content in `content_items` for all 3 brands, 3 `brand_snapshots` with `sample_size > 0`, trend points committed, `GET /analyses/{id}/dashboard` -> 200 with `target.brand.role == "target"` and 2 competitors.
- `export_openapi --check` and `validate_golden` pass. Frontend not touched.

Method: read code, ran backend tests (with a local Postgres), ran the real `run_analysis`, `run_investigation` and API routes against Postgres with scripted SerpApi fixtures and a stub sentiment model, ran frontend typecheck/lint/tests/build, and tested live (non-golden) mode.

Test baseline: no Postgres = 870 passed / 230 skipped. With Postgres = 1092 passed / 5 failed / 3 skipped (torch missing). Frontend: tsc clean, lint clean, 21 vitest pass, `next build` ok.

Items marked (code-read) were not executed. Everything else was reproduced.

---

## [CRITICAL] DetachedInstanceError in run_analysis - FIXED and VERIFIED

File: backend/app/pipeline/analysis_pipeline.py
Location: run_analysis lines 305-317 (also 409, 455)

Problem: Analysis ends `failed`, stuck at stage `planning`, error "Analysis failed. Check server logs for details." Traceback: `DetachedInstanceError ... _window_set(analysis)`.
Root Cause: `session.commit()` expires `analysis` (default expire_on_commit=True), the `with Session` block then closes, and `analysis.as_of_date`, `.product`, `.serp_calls_budget` are read on the detached, expired instance. Same pattern at line 409 (`analysis.category` after the commit at 402) and line 455 (`_snapshot(engine, analysis, ...)` reads `analysis.id` after the commit at 453).
Impact: Every analysis fails. The app produces no data.

Required Fix: Read needed scalars into locals or a small dataclass inside the session (as_of_date, period_days, window dates, product, category, serp_calls_budget) and use those afterwards. Do not pass ORM instances out of a session. Optionally use `expire_on_commit=False`.
Suggested Test: Postgres integration test that creates an analysis and calls `run_analysis` with `ScriptedTransport` + `StubSentimentAnalyzer`; assert status `completed`/`partial`, stage `done`.

Fix (verified): `run_analysis` now copies the needed scalars into a frozen `_RunContext` (windows, product, category, serp_calls_budget) and `_BrandCtx` values (id, name, role) while the session is open; no ORM instance is read after a commit or session close. `_analyze_brand` and `_snapshot` take ids/contexts instead of `Analysis` or `Brand` objects. Tests: `tests/integration/test_analysis_pipeline_e2e.py` (`test_full_analysis_with_two_competitors_completes`, `test_run_context_survives_session_close_and_commit`).

---

## [CRITICAL] Phase-5 repositories take Session but pipeline passes Engine - FIXED and VERIFIED

File: backend/app/db/repositories/phase5.py; backend/app/pipeline/analysis_pipeline.py
Location: phase5.py classes TrendPointRepository, BrandSnapshotRepository, SignalRepository; pipeline lines 113, 300, 448

Problem: `AttributeError: 'Engine' object has no attribute 'add_all'` at `_persist_trends`. Reproduced for trend points. Snapshot and signal repos have the same constructor and are called with `engine` too.
Root Cause: These three repos are Session-based and only `flush()`. Every other repository is Engine-based and commits itself. The pipeline treats them all as Engine-based.
Impact: Analysis fails after collection. Even if given a Session, nothing is committed.

Required Fix: Make the three repos Engine-based (open a Session, add, commit), matching the other repositories.
Suggested Test: Repository tests using a real engine; assert rows are visible from a second session after the call.

Fix (verified): `TrendPointRepository`, `BrandSnapshotRepository` and `SignalRepository` in `backend/app/db/repositories/phase5.py` now take an `Engine`, run each call in its own short transaction and commit, like the other repositories. Sessions use `expire_on_commit=False` and refresh server defaults, so returned rows stay readable. Tests: `tests/integration/test_phase5_repositories.py` (rows visible from a separate connection; snapshot upsert inserts then updates).

---

## [CRITICAL] _snapshot unpacks (ContentItemRow, ContentAnalysisRow) rows incorrectly - FIXED and VERIFIED

File: backend/app/pipeline/analysis_pipeline.py
Location: _snapshot line 235

Problem: `AttributeError: id` at `ItemAspectRow.content_id.in_([r.id for r in rows])`. Analysis fails at stage `snapshotting`.
Root Cause: `rows` holds `Row(ContentItemRow, ContentAnalysisRow)` tuples; `r.id` is read on the tuple.
Impact: No snapshots, no dashboard.

Required Fix: `[r.id for r, _ in rows]`.
Suggested Test: `_snapshot` test with at least one analyzed item per window; assert non-zero `sample_size`.

Fix (verified): `[r.id for r, _ in rows]`. Test: `test_snapshot_counts_items_per_window` (non-zero `sample_size` and `baseline_sample_size`, aspect scores present).

---

## [CRITICAL] Enum identity checks (`is`) between two different enum classes - FIXED and VERIFIED

File: backend/app/pipeline/analysis_pipeline.py; backend/app/api/v1/analyses.py
Location: pipeline lines 222, 223, 224, 258, 322; analyses.py lines 451, 474, 476

Problem: Competitors are never planned or fetched (DB held content only for the target brand). Every brand snapshot has `sample_size=0` and `baseline_sample_size=0` with nonsense health (overall 70, sentiment 100, risk 100). `GET /analyses/{id}/dashboard` returns 500 (`StopIteration` at `next(... if ab.role is BrandRole.target)`).
Root Cause: ORM columns return `app.db.models.enums.*` members; the code compares with `app.schemas.domain.*` members using `is`. They are different classes (`==` is True, `is` is False).
Impact: Competitor analysis is silently absent, all metrics are zero, dashboard is unusable.

Required Fix: Compare with `==`, or make the ORM and API layers share one enum definition. Grep all `is <Enum>.` uses on ORM values.
Suggested Test: End-to-end run with two competitors; assert competitor rows exist in `content_items`, snapshots have non-zero sample sizes, and the dashboard returns 200.

Fix (verified): all `is <Enum>.x` checks on ORM values in `analysis_pipeline.py` (window filters in `_snapshot`, competitor filter in `run_analysis`) and `analyses.py` (dashboard target/competitor selection and `snap_block`) now use `==`. Grep of `backend/app` found no other identity checks on ORM enum values (the remaining ones in `processing/processor.py`, `schemas/` and `serpapi/` compare members of one class). Tests: the end-to-end tests above, plus `tests/unit/test_enum_comparisons.py`, which also fails if an `is <Enum>.member` check returns in those two files.

---

## [CRITICAL] Dashboard passes AnalysisBrand row as `role` - FIXED and VERIFIED

File: backend/app/api/v1/analyses.py
Location: get_dashboard, `target=snap_block(*target)` (line ~488)

Problem: After the enum fix the dashboard still returns 500: `ValidationError ... BrandRef.role ... input_type=AnalysisBrand`.
Root Cause: `target` is a `(Brand, AnalysisBrand)` tuple; `snap_block(b, role)` receives the `AnalysisBrand` as `role`.
Impact: Dashboard 500 for every completed analysis.

Required Fix: `snap_block(target[0], target[1].role)`.
Suggested Test: API test: completed analysis -> `GET /dashboard` returns 200 and `target.brand.role == "target"`.

Fix (verified): `snap_block(target[0], target[1].role)`. Test: `test_dashboard_returns_200_after_full_run` (200, `target.brand.role == "target"`, 2 competitors with role `competitor`, all with `sample_size > 0`).

---

## [CRITICAL] run_investigation uses expired ORM objects after the session closes - FIXED and VERIFIED

File: backend/app/pipeline/investigation_pipeline.py
Location: run_investigation lines 54-68 and later uses (`brand.name`, `analysis.product`, `analysis.id`, `sig.aspect`, `sig.signal_score`)

Problem: Investigation row ends `failed` at step `generating_queries`.
Root Cause: Same as the run_analysis bug: `s.commit()` expires `inv/sig/analysis/brand`, session closes, attributes are then read.
Impact: Every investigation fails.

Required Fix: Copy needed scalars into locals inside the session.
Suggested Test: Integration test: seed a signal, call `run_investigation`, assert status `completed`.

Fix (verified): `run_investigation` copies `analysis.id`, `analysis.product`, `brand.id`, `brand.name` into locals and the signal columns the services use into a frozen `_SignalCtx` (aspect, signal_score, signal_confidence, impact) before the first `commit()`. Nothing reads an ORM instance after the session closes; the evidence and content queries also use `select()` inside their own sessions. Tests: `test_full_investigation_completes_and_get_is_200_throughout`, `test_investigation_with_no_evidence_still_completes`.

---

## [CRITICAL] Investigation step states do not match the API enum - FIXED and VERIFIED

File: backend/app/pipeline/investigation_pipeline.py
Location: _steps (lines 25-47); schemas/domain.py StepState

Problem: `GET /investigations/{id}` returns 500: `ValueError: 'running' is not a valid StepState`.
Root Cause: Backend writes `completed` / `running` / `pending`; `StepState` is `done` / `active` / `pending`.
Impact: Every poll of any running or finished investigation 500s.

Required Fix: Emit `done` and `active`.
Suggested Test: Run an investigation, `GET` it at each step and at the end; assert 200 and valid states.

Fix (verified): `_steps` emits `done` / `active` / `pending`. The terminal `done` step marks every step `done` (previously the last step would have stayed active). Step changes go through one `_set_step` helper, and the declared `recommending` step is now actually entered before recommendations are generated. Tests: `test_full_investigation_completes_and_get_is_200_throughout` (GET 200 after each of the 6 transitions, states checked against `StepState`, final state all `done`), plus 3 unit tests on `_steps`.

---

## [CRITICAL] `.priority.value` on a plain string in recommendations - FIXED and VERIFIED

File: backend/app/pipeline/investigation_pipeline.py
Location: line 230

Problem: `AttributeError: 'str' object has no attribute 'value'`; the investigation fails at `synthesizing`.
Root Cause: `Recommendation.priority` is `Text`, so the stored value is a `str`.
Impact: Every investigation fails after synthesis.

Required Fix: Use `r.priority` directly (or make the column an enum consistently).
Suggested Test: Same investigation integration test as above.

Fix (verified): the report uses `r.priority` directly (the column stays `Text`). Test: `test_full_investigation_completes_and_get_is_200_throughout` asserts `priority` in `{high, medium, low}` in the stored report and the API response.

---

## [CRITICAL] UUID objects written into JSONB investigation report - FIXED and VERIFIED

File: backend/app/pipeline/investigation_pipeline.py
Location: report["recommendations"] (lines 227-238) and `inv.report = report` (line 241)

Problem: `TypeError: Object of type UUID is not JSON serializable` on commit.
Root Cause: `id` and `evidence_ids` are `UUID` objects; psycopg's JSON dumper cannot serialize them. Competitor comparison refs also carry UUIDs.
Impact: Every investigation fails when saving the report.

Required Fix: Convert to `str` before assigning (e.g. `json.loads(json.dumps(report, default=str))` or `model_dump(mode="json")`).
Suggested Test: Complete an investigation with recommendations and read the report back via `GET /investigations/{id}`.

Fix (verified): the report goes through `pydantic_core.to_jsonable_python` before it is assigned to `inv.report`, so recommendation ids, evidence ids and the competitor-comparison brand refs are stored as strings. Recommendation `evidence_ids` are passed through as the stored strings. Tests: the full-run test reads the report back from JSONB (ids are `str`) and through `GET /investigations/{id}`, including `competitor_comparison.rows[].brand`.

---

## [CRITICAL] Frontend server components fetch a relative URL (live mode) - FIXED (NOT FULLY VERIFIED)

File: frontend/lib/api/client.ts; frontend/app/{dashboard,signals,investigate,evidence,competitors}/[id]/page.tsx
Location: `request()` line 42: `fetch(`/api/v1${path}`)`

Problem: With `NEXT_PUBLIC_USE_GOLDEN=false`, `/signals/abc` returns 500 and logs `TypeError: Failed to parse URL from /api/v1/...`. The dashboard hits the same error (shown only via its error boundary).
Root Cause: Those pages are async Server Components. Server-side `fetch` needs an absolute URL; the relative `/api` rewrite only works in the browser.
Impact: No live data page can render. Only golden mode works.

Required Fix: Use an absolute base on the server (`API_ORIGIN` + `/api/v1`) and keep the relative path in the browser, or move data fetching into client components.
Suggested Test: Frontend test or smoke script that starts `next start` with `USE_GOLDEN=false` against a stub API and requests each page.

Fix (implemented): `client.ts` now uses a relative `/api/v1` URL in the browser and `API_ORIGIN` plus `/api/v1` for Server Components. `API_ORIGIN` defaults to `http://127.0.0.1:8000`. Frontend live-mode smoke/type validation remains pending because npm dependencies are unavailable in this sandbox.

---

## [HIGH] Analysis job silently dropped when another job is running - FIXED (NOT YET VERIFIED)

File: backend/app/pipeline/jobs.py; backend/app/config/settings.py
Location: start_analysis_job lines 20-26; `max_concurrent_analyses`

Problem: If the semaphore is held, the function returns without doing anything. The analysis stays `queued` forever. `max_concurrent_analyses` is never used.
Root Cause: Non-blocking `acquire` with silent return; `BoundedSemaphore(1)` hard-coded.
Impact: A second request during a run never executes; the UI polls indefinitely.

Required Fix: Reject at the API with 409 when a job is running, or queue/wait; mark the row `failed` with a reason if dropped; honor the setting.
Suggested Test: Start two analyses back to back; assert the second either runs after the first or is rejected with a clear error.


Fix (unverified): `start_analysis_job` waits for a free slot instead of returning. The gate (`_Gate`) reads `Settings.max_concurrent_analyses` on every call, so the setting is honored. A job that gets no slot within `QUEUE_WAIT_SECONDS` (30 min, below the 60 min reaper cutoff) marks its row `failed` ("...the server stayed busy..."), and an exception that escapes `run_analysis` also marks the row `failed`; the slot is always released. Decision: queue rather than reject with 409, because API.md 3.1 lists no 409 for a busy server. Tests: `tests/unit/test_jobs_concurrency.py` (waits then runs, limit 2 honored, timeout fails the row, crash releases the slot, 8 queued jobs run one at a time), `tests/integration/test_jobs_and_signals_api.py` (3 concurrent real analyses all end completed/partial with peak concurrency 1, back-to-back `POST /analyses`, timeout and crash rows end `failed`).
---

## [HIGH] Stale-job reaper is never called - FIXED (NOT YET VERIFIED)

File: backend/app/pipeline/jobs.py
Location: reap_stale_jobs

Problem: No caller exists anywhere (grep).
Root Cause: Never wired into startup or a route.
Impact: A server restart mid-run leaves analyses `running` forever.

Required Fix: Call it on app startup (lifespan) and/or before creating an analysis.
Suggested Test: Insert a `running` row older than the cutoff, start the app, assert it becomes `partial`/`failed`.


Fix (unverified): `reap_stale_jobs_safe` (never raises, no-op without a database) runs in the app lifespan startup, in `create_analysis` before the row is created and in `investigate_signal`. `reap_stale_jobs` now moves `running` analyses older than 60 min to `partial`, `queued` analyses older than 60 min to `failed`, and `queued`/`running` investigations older than 60 min to `failed` (then recomputes the signal status), because a stuck investigation row would otherwise block every later one. Fresh rows are untouched. Tests: `test_reaper_recovers_stale_rows_and_leaves_fresh_ones`, `test_app_startup_runs_the_reaper`, `test_startup_without_a_database_does_not_fail`, `test_creating_an_analysis_reaps_stale_rows`, `test_reaper_fails_stale_investigations_and_resets_the_signal`.
---

## [HIGH] POST /signals/{id}/investigate ignores its contract - FIXED (NOT YET VERIFIED)

File: backend/app/api/v1/signals.py
Location: investigate_signal (lines 92-136), get_signal (lines 51-72)

Problem: `X-Access-Code` is declared but never checked. No 409 (`signal_not_investigable`, `investigation_in_progress`), no 429 or limits. Unbounded daemon threads are started. `Signal.status` is never set to `investigating`/`investigated`. A previously failed investigation is returned as `reused` unless `force=true`. `GET /signals/{id}` always returns `latest_investigation=None` and hard-codes `role=target` even for competitor signals.
Root Cause: Endpoint implemented without the API.md error and state behavior.
Impact: Documented contract unmet; duplicate or concurrent runs; stuck UI.

Required Fix: Implement the documented checks, a single-flight guard, status transitions, populate `latest_investigation`, and use the real brand role. Do not reuse failed investigations.
Suggested Test: API tests for each documented status code; second call while running returns 409; signal status transitions after completion.


Fix (unverified): `investigate_signal` follows API.md 3.7: demo ids -> 200 reuse of the bundle; 404 unknown/malformed; 501 without a database; 429 `rate_limited`; 409 `signal_not_investigable` unless the analysis is `completed`/`partial`; an active (`queued`/`running`) investigation is returned with 200 `reused: true`, or 409 `investigation_in_progress` with `force=true`; the newest `completed` one is reused with 200 unless `force`; failed ones are never reused. A new investigation needs `X-Access-Code` (403 `live_access_required`) and SerpApi quota (429 `serpapi_quota_low`) only when live SerpApi is enabled and `SERP_BUDGET_PER_INVESTIGATION > 0`; the current pipeline spends no credits, so `live_data_disabled` is not emitted. The signal row is locked (`SELECT ... FOR UPDATE`) while the decision and insert happen, so concurrent calls create exactly one investigation. Threads are replaced by `BackgroundTasks` + `start_investigation_job` (same bounded gate as analyses). `Signal.status` is `investigating` on create and is recomputed by `settle_signal_status` when the investigation completes (`investigated`) or fails (`detected`, or `investigated` if an older one completed). `GET /signals/{id}` fills `latest_investigation` (newest by creation time) and returns the real brand role from `analysis_brands` (competitor signals are no longer reported as `target`). Tests: `tests/integration/test_jobs_and_signals_api.py` (each status code, reuse, force, failed-not-reused, older-completed-over-newer-failed, 4-way race -> one row, access code, quota, status transitions, `latest_investigation`, target vs competitor role, real end-to-end run). Not changed: the frontend start/poll flow (separate open item below).
---

## [HIGH] Frontend cannot start an investigation; backend never reports one - FIXED (NOT FULLY VERIFIED)

File: frontend/lib/api/client.ts; frontend/app/investigate/[id]/page.tsx; backend/app/api/v1/signals.py
Location: no `investigateSignal` in client.ts/hooks.ts; page line 23-31

Problem: Nothing in the frontend calls `POST /signals/{id}/investigate`. The investigate page shows "Live investigations arrive in a later phase" whenever `latest_investigation` is null, and the backend always returns null. The page is a one-shot server render with no polling.
Root Cause: Missing client function and UI action; backend field not populated.
Impact: The live investigation flow is unreachable end to end.

Required Fix: Add the client function and a start/poll UI (client component); populate `latest_investigation`.
Suggested Test: Frontend test for the start -> poll -> report flow with a stubbed API; backend test that `latest_investigation` is set after a run.

Fix (implemented): added `investigateSignal()` to the frontend API client and a client-side `InvestigationRunner` that starts the investigation, polls every 2 seconds, handles API errors/access codes, and refreshes the report when terminal. Backend `latest_investigation` is already populated by the prior fix. Browser validation remains pending.

---

## [HIGH] Synthesizer prompt omits the evidence; uncited findings are kept - FIXED and VERIFIED

File: backend/app/services/investigation/synthesizer.py
Location: synthesize lines 4-35 (code-read)

Problem: The prompt contains only the aspect and score, no evidence list or IDs. The LLM cannot cite real IDs, so findings with IDs are dropped. The filter `all(str(x) in valid for x in f.get("evidence_ids", []))` passes any finding whose `evidence_ids` is empty, so uncited claims survive. `scope` and other fields from the LLM are not validated.
Root Cause: Incomplete prompt and filter.
Impact: Violates "LLM may cite evidence IDs only; uncited claims are dropped"; reports are empty or unsupported.

Required Fix: Include evidence IDs plus short content in the prompt; drop findings and recommendations with no valid IDs; validate the output shape.
Suggested Test: Unit test with a fake provider returning (a) valid IDs, (b) invalid IDs, (c) empty IDs; only (a) survives.

Fix (verified): `build_prompt` lists up to 20 evidence items as JSON (`id`, `stance`, `relevance`, note cut to 300 chars) and tells the model to cite only those IDs; the system prompt marks the evidence as untrusted data. A finding or recommendation is kept only if `evidence_ids` is a non-empty list and every ID is in the stored evidence set (IDs de-duplicated, order kept). Findings need non-empty `text`, recommendations need `title` and `action`, `scope` must have a valid verdict and explanation (otherwise `unknown`), and a missing summary or no surviving finding switches to the deterministic fallback report, which cites only supplied evidence. Tests: `tests/unit/test_investigation_synthesizer.py` (valid / invalid / empty / mixed / malformed shapes) and `test_llm_report_keeps_valid_evidence_ids_and_drops_invalid_or_uncited` (fake Groq provider reading the IDs out of the real prompt; stored report keeps exactly the valid finding with its IDs in order).
Not changed (still open under other items): the pipeline still replaces the model's `scope` and `recommendations` with the deterministic ones, and `recency`/`consistency` confidence inputs remain placeholders.

---

## [HIGH] Investigation failures are swallowed with no logging - FIXED and VERIFIED

File: backend/app/pipeline/investigation_pipeline.py
Location: except block lines 247-254

Problem: Exception is caught, status set to `failed`, no traceback logged.
Root Cause: Missing `logger.exception`.
Impact: All four investigation bugs above were invisible in logs.

Required Fix: Log with `logger.exception` and the investigation id.
Suggested Test: Force a failure; assert a log record with the exception is emitted.

Fix (verified): the `except` block calls `logger.exception("Investigation %s failed", investigation_id)` before recording `failed`; the user-facing `error` text is unchanged. The synthesizer's fallback now logs a warning with the exception type. Test: `test_failure_logs_traceback_and_marks_failed_with_get_200` (log record with `exc_info`, the investigation id and the original `RuntimeError`; row `failed`; `GET` returns 200).

---

## [HIGH] Demo mode is incomplete - FIXED (NOT YET VERIFIED)

File: backend/app/api/v1/analyses.py; signals.py; usage.py
Location: list_mentions, estimate_analysis, investigate_signal, get_usage

Problem: With `DEMO_MODE=true` and no database: `GET /analyses/demo/mentions` -> 404, `GET /usage` -> 501, `POST /analyses/estimate` -> 501, `POST /signals/demo-signal-battery/investigate` -> 404. The frontend hides this only by short-circuiting demo ids client-side.
Root Cause: Demo aliases are handled in some routes only.
Impact: The documented "no database, no model, no network" demo breaks on aspect drill-down, quota banner and investigate.

Required Fix: Serve demo data from the bundle for these routes (mentions, usage, estimate, investigate).
Suggested Test: A DEMO_MODE API test hitting every route with the demo aliases.


Fix (unverified): with `DEMO_MODE=true` and no database, `GET /analyses/{demo}/mentions` is built from the bundle's evidence items (all negative, aspect `battery`; `aspect`, `sentiment`, `source_type`, `brand_id` and paging work), `GET /usage` returns a zero-spend response, `POST /analyses/estimate` computes the real plan and reports every call as served from the bundle (`estimated_new_calls: 0`, `can_run: true`), and `POST /signals/{demo}/investigate` returns 200 `reused: true` pointing at the bundled investigation. With a database configured, or with `DEMO_MODE` off, these routes behave as before. The bundle JSON was not changed. Tests: `tests/unit/test_demo_mode_api.py` (every documented demo route plus the demo-off 404/501 cases).
---

## [HIGH] Pipelines and routes are untested; migration tests are red with a database - FIXED (NOT YET VERIFIED)

File: backend/tests/**; backend/tests/integration/test_migrations.py; backend/alembic/env.py
Location: whole test suite

Problem: No test references `run_analysis`, `run_investigation`, `create_analysis`, the dashboard or investigate routes, which is why the critical bugs passed. With Postgres, 5 migration tests fail: head is `0010` but tests expect `0004`/`0006`, and `test_models_match_migrated_schema` reports drift (llm_calls, evidence, investigations, recommendations).
Root Cause: Tests stale after later phases; `env.py include_object` hides objects the test does not hide.
Impact: Green CI-without-DB hides broken flows; the DB suite is red.

Required Fix: Add the end-to-end tests above; update migration tests to the current head and table set; make the drift test use the same `include_object` rules (or fix the model/migration mismatch).
Suggested Test: The suites themselves, run in CI with a Postgres service.


Fix (unverified): the pipeline end-to-end tests were added in the earlier sessions; this session adds the jobs/signals/investigate API tests and the demo-mode tests listed above, and updates `tests/integration/test_migrations.py` to head `0010`: expected version, the full 16-table set (with `llm_calls`, `investigations`, `evidence`, `recommendations`), a row-level-security test for every table, explicit per-revision downgrade tests (0008...0004) and a one-step 0010 -> 0009 test instead of the stale `-1 -> 0004`. The drift test now uses the same `include_object` as `alembic/env.py`; the function moved to `app/db/migration_filters.py` and both import it. The five failures listed earlier match: head version (x2), table set, drift, `-1` downgrade. Remaining honesty note: if `test_models_match_migrated_schema` still reports differences for evidence/investigations/recommendations, that is a real model/migration mismatch that was not found by reading the code.
---

## [MEDIUM] CI workflow file is empty - FIXED (NOT FULLY VERIFIED)

File: .github/workflows/ci.yml
Location: whole file (0 bytes)

Problem: No CI runs.
Root Cause: File was never filled.
Impact: No automatic test, lint or contract check.

Required Fix: Add a workflow: backend pytest with a Postgres service, ruff, `export_openapi --check`, `validate_golden`, frontend typecheck/lint/test/build.
Suggested Test: Push and confirm the workflow runs green.

Fix (implemented): `.github/workflows/ci.yml` now runs backend PostgreSQL tests, Ruff, OpenAPI/golden checks, and frontend typecheck/lint/test/build on pushes and pull requests to `main`. A GitHub Actions run is still required for verification.

---

## [MEDIUM] backend/.env.example is a copy of README.md - FIXED (NOT FULLY VERIFIED)

File: backend/.env.example
Location: whole file (2082 bytes, identical in size to README.md)

Problem: It contains README text and no variables.
Root Cause: Wrong content committed.
Impact: `cp .env.example .env` gives no DATABASE_URL, SERPAPI_API_KEY, GROQ_API_KEY etc.; `alembic upgrade head` fails with "No database URL".

Required Fix: Replace with placeholder values for every `Settings` field.
Suggested Test: Test that every `Settings` field name appears in `.env.example`.

---

## [MEDIUM] Demo scripts are empty files - FIXED (NOT FULLY VERIFIED)

File: backend/scripts/seed_demo.py, probe_demo_signal.py, warm_demo_cache.py (and the root scripts/ copies)
Location: whole files (0 bytes)

Problem: DATABASE.md and DEVELOPMENT_PLAN say `seed_demo.py` loads the golden fixture into the DB; the scripts do nothing.
Root Cause: Not implemented.
Impact: No DB-backed demo seed; the demo cache cannot be warmed.

Required Fix: Implement them or remove the references from the docs.
Suggested Test: Run `seed_demo.py` on a blank DB and fetch the dashboard.

Fix (implemented): `seed_demo.py` now creates an idempotent fixed-ID DB-backed Samsung demo scenario; `probe_demo_signal.py` validates the demo spike; `warm_demo_cache.py` imports pinned bundle cache entries when present and safely no-ops when the bundle has none. PostgreSQL execution remains pending.

---

## [MEDIUM] Stale duplicate root-level tests/ and scripts/ - FIXED and VERIFIED

File: tests/, scripts/ (repo root) vs backend/tests, backend/scripts
Location: e.g. tests/conftest.py, scripts/export_openapi.py differ from the backend copies

Problem: Two diverging copies; `scripts/check_type_contract.py` exists only at the root.
Root Cause: Leftover copy.
Impact: Confusion about the canonical files; stale tests can mislead.

Required Fix: Keep one tree under `backend/` and move `check_type_contract.py` into it (or into a clear root `scripts/`).
Suggested Test: CI runs only the canonical tests.

Fix (verified): removed root-level duplicate `tests/` and `scripts/` trees; canonical copies live under `backend/tests` and `backend/scripts`, including `check_type_contract.py`. Documentation paths were updated.

---

## [MEDIUM] llm_calls is never written; LLMCall excluded from metadata - FIXED (NOT FULLY VERIFIED)

File: backend/app/db/models/__init__.py; backend/alembic/env.py; backend/app/services/llm/*
Location: `# from app.db.models.llm_call import LLMCall`; `include_object`

Problem: No code logs LLM calls. `LLMLimiter` and `llm_max_concurrency` are unused. `include_object` hides `llm_calls` and the `fk_serp_usage_investigation` constraint, masking real drift.
Root Cause: Phase 6 LLM audit logging and concurrency control were left unfinished.
Impact: No LLM audit trail or concurrency cap; schema drift undetected.

Required Fix: Register the model and write a row per Groq call, or remove the table and settings; remove the `include_object` hacks.
Suggested Test: Run an investigation with a fake provider; assert one `llm_calls` row per call.

---

## [MEDIUM] Investigation confidence uses fabricated inputs - FIXED (NOT FULLY VERIFIED)

File: backend/app/pipeline/investigation_pipeline.py
Location: compute_confidence call (lines 187-194)

Problem: `recency=0.8` is a constant and `consistency=agreement` duplicates another factor.
Root Cause: Placeholders left in.
Impact: 25% of the weight is not derived from evidence, contrary to the documented deterministic formula.

Required Fix: Compute recency from evidence dates and consistency from cross-source agreement.
Suggested Test: Unit test: different evidence dates give different recency.

---

## [MEDIUM] Analysis ignores product relevance and corroboration inputs - FIXED (NOT FULLY VERIFIED)

File: backend/app/pipeline/analysis_pipeline.py
Location: `_analyze_brand` line 142, `_metric_rows` line 195, trend/snapshot fields

Problem: `BrandProfile(products=(), aliases=())` ignores `analysis.product`. `is_about_brand=True` is hard-coded. `interest_change_pct`, `trend_corroborated` and the dashboard `search_interest` are always empty even though trend points are stored.
Root Cause: Features not wired.
Impact: Off-topic items count as brand mentions; the trend chart and corroboration never appear.

Required Fix: Pass product/aliases; use the stored relevance flag; compute interest change and corroboration from trend points.
Suggested Test: Test with an off-topic item and with trend data; assert exclusion and a non-null interest change.

---

## [MEDIUM] Signal/investigation routes return 500 when no database is configured - FIXED and VERIFIED

File: backend/app/api/v1/signals.py; investigations.py
Location: `get_engine(settings.database_url or settings.database_url_direct)` (code-read)

Problem: With empty URLs, `create_engine("")` raises and the response is 500; the analyses routes return 501 for the same case.
Root Cause: No guard.
Impact: Inconsistent, misleading error.

Required Fix: Reuse the `_engine()` guard.
Suggested Test: Request a UUID signal with no DB configured; expect 501.

Fix (verified): both investigation GET routes now explicitly return the documented 501 error when no database URL is configured; 26 targeted jobs/signals/demo/hardening tests pass.

---

## [MEDIUM] Evidence stance and relevance are keyword heuristics - RESOLVED BY DOCUMENTED MVP SCOPE

File: backend/app/services/investigation/evidence_scorer.py
Location: score_evidence

Problem: Stance is set by word lists and relevance is a constant (0.35 / 0.85). AGENTS.md assigns stance tagging to Groq. `generate_queries` output is discarded and investigation spends no SerpApi credits.
Root Cause: Simplified implementation.
Impact: Weak evidence quality; docs and behavior disagree.

Required Fix: Implement the documented behavior, or update AGENTS.md/docs to state the heuristic scope.
Suggested Test: Scoring tests against labeled sample items.

Resolution: the MVP investigation path is deliberately cache-safe and deterministic. `generate_queries` provides bounded local templates, existing stored evidence is scored deterministically, and Groq is used for synthesis/reasoning when configured. The architecture/docs were updated so behavior no longer claims an unimplemented Groq stance-tagging/live-evidence stage.

---

## [LOW] First session block in run_analysis is outside the try - FIXED (NOT FULLY VERIFIED)

File: backend/app/pipeline/analysis_pipeline.py
Location: lines 304-314

Problem: A DB error before the `try` leaves the row `queued`/`running`.
Root Cause: Error handling starts too late.
Impact: Stuck status on early failures.

Required Fix: Move the first block into the `try`.
Suggested Test: Simulate a DB error at start; assert status `failed`.

Fix (implemented): the initial engine/session/context block is now protected by an explicit startup try/except; when an engine exists, queued/running rows are marked failed and the exception is logged. Full DB fault-injection verification remains pending.

---

## [LOW] Live SerpApi calls are unauthenticated when LIVE_ACCESS_CODE is empty - FIXED (NOT FULLY VERIFIED)

File: backend/app/api/v1/analyses.py
Location: create_analysis lines 211-220

Problem: The access code is enforced only if configured.
Root Cause: Optional guard.
Impact: With `ALLOW_LIVE_SERPAPI=true` and no code, any client can spend credits (daily cap still applies).

Required Fix: Require a code (or refuse live mode) whenever live calls are enabled.
Suggested Test: Live enabled, no code -> request is rejected.

Fix (implemented): when live SerpApi access is enabled for an investigation, a configured access code is now mandatory; an empty configured code no longer disables the guard. Integration verification remains pending.

---

## Summary

Total issues: 29. All 29 issues now have an implementation or explicit documented-scope resolution in this checkpoint. Verification is split between fully verified prior PostgreSQL tests, targeted tests run here, and environment-limited checks that still require a real development machine.

- Core analysis pipeline: **FIXED and VERIFIED**
- Investigation pipeline: **FIXED and VERIFIED**
- Remaining orchestration/API/demo/hardening: **FIXED - NOT FULLY VERIFIED** where PostgreSQL execution was required
- Frontend live flow: **IMPLEMENTED - NOT FULLY VERIFIED** pending npm/browser validation
- CI: **IMPLEMENTED - NOT FULLY VERIFIED** pending a GitHub Actions run
- Overall Status: **READY FOR FINAL REAL-MACHINE VALIDATION; NOT YET CLAIMED PRODUCTION-READY**

### Verification performed in this checkpoint

- Backend unit suite excluding the environment-only PostgreSQL refusal test: **873 passed, 1 deselected**.
- Targeted jobs/signals/demo/hardening tests: **26 passed**.
- Full backend suite without PostgreSQL: **938 passed, 288 skipped, 1 deselected**.
- `export_openapi.py --check`: **pass**.
- `validate_golden.py`: **pass**.
- `check_type_contract.py`: **pass** (75 OpenAPI schemas covered).
- Python compilation of backend application, scripts, and tests: **pass**.
- Frontend typecheck/lint/test/build: **not runnable in this sandbox because `node_modules` is absent and outbound npm installation is blocked**.
- PostgreSQL integration suite: **not runnable in this sandbox because `psycopg`/PostgreSQL are unavailable**.
- Ruff: **not runnable in this sandbox because the `ruff` package is unavailable**.

The previous PostgreSQL checkpoints remain the source of truth for the already-verified core pipeline and investigation end-to-end behavior.
