# BrandPulse AI — Development Progress

> **Evidence basis for this version (2026-10-06):** the repo was inspected as an extracted zip (`BrandPulse-AI-main.zip`, **no `.git` directory**). Verified by running: backend tests (70 passed against a local PostgreSQL 16, incl. 31 migration tests; 39 pass + 31 skip without `TEST_DATABASE_URL`), `ruff check` and `ruff format --check` (clean), `alembic upgrade head` + `alembic check` on a blank database, a real `uvicorn` server answering `/api/v1/health` with `database: ok` against that migrated database, `docs/*.md` (except this file) byte-identical to the uploaded copies. Not verifiable here: git state, Supabase itself (pooler, RLS), CI, accounts/keys.
> Anything not listed as verified below stays **NOT STARTED** or **UNKNOWN**. **First action of any agent with repo access: inspect the repo, then correct this file.** Never assume a planned feature exists.

---

## 1. Current Status

```text
MVP STATUS: PHASES 0-2 IMPLEMENTED IN CODE; GOLDEN DEMO READY; PHASE 2 NOT YET VERIFIED BY REAL pytest/Ruff/PostgreSQL; EXTERNAL ACCOUNTS PENDING
CURRENT PHASE: 2 (SerpApi layer and budget machinery) IMPLEMENTED, verification pending on a machine with dependencies; Phase 0 external account setup still pending
CURRENT MILESTONE: M1 (Clickable demo): full golden journey implemented; manual visual check on desktop/mobile pending
OVERALL COMPLETION: Phases 0-2 implemented (Phase 0 accounts, Phase 1 visual check and Phase 2 live probe/verification pending); Phases 3-10 not started
LAST UPDATED: 2026-10-07
```
## 2. Executive Summary

- **Works (verified from the user's Windows run):** backend dependencies installed, OpenAPI is current, 155 tests passed and 31 migration tests skipped without `TEST_DATABASE_URL`, Ruff check/format passed, Uvicorn started, and `/api/v1/health` returned 200.
- **Implemented in this pass:** golden Samsung fixture + formula tests, deterministic scoring helpers, Next.js/TypeScript/Tailwind frontend, typed API client with golden mode, golden dashboard → investigation → evidence flow, scoring/design docs, CI workflow, frontend/backend module READMEs, and contract coverage checks.
- **Not externally completed:** Supabase, SerpApi, and Groq account creation/keys. No live calls were made.
- **Frontend verification (Phase 1 pass):** npm access worked; `npm ci`, typecheck, lint, test (21 passed) and build all pass, and a `next start` smoke test returned 200 on all 8 golden routes.
- **Can it be demonstrated?** Yes. Golden mode needs only the frontend (see section 7b); no external credits are required.
## 3. Phase Progress

| Phase | Name | Status | Key Result |
|------|------|--------|------------|
| 0 | Foundations and contracts | IMPLEMENTED / EXTERNAL SETUP PENDING | Backend contracts, golden fixture, frontend golden flow, docs and CI scaffold are present |
| 1 | Frontend on golden data | IMPLEMENTED (visual check pending) | Landing → analyze (estimate + confirm dialog) → simulated progress → dashboard (health, sentiment, aspect drawer, trend, signal card) → investigation → evidence → competitors; states + 21 frontend tests |
| 2 | SerpApi layer and budget machinery | IMPLEMENTED (unverified by real pytest/Ruff/PG; no live probe yet) | Migration `0002`, client, cache, budget/usage, estimator, planner, 5 parsers, synthetic fixtures, safe recorder script. See sections 11, 18, 22 |
| 3 | Processing and persistence | NOT STARTED | — |
| 4 | Local NLP | NOT STARTED | — |
| 5 | Signals, scoring and brand health | NOT STARTED | Formula primitives only; pipeline not implemented |
| 6 | Analysis pipeline and first real end-to-end | NOT STARTED | — |
| 7 | Groq and investigation | NOT STARTED | Golden report only; live investigation not implemented |
| 8 | Competitors and recommendations | NOT STARTED | Golden display only |
| 9 | Hardening and testing | NOT STARTED | — |
| 10 | Demo bundle, pre-warm, polish and rehearsal | NOT STARTED | — |
## 4. Current Phase

### Goal
Phase 2: SerpApi layer and budget machinery (cache, usage counting, 250/month guard, estimator, planner, parsers) with no live calls.

### Current module
`backend/app/services/serpapi/` (+ `app/schemas/serp.py`, `app/db/models/serp.py`, `app/db/repositories/serp_*.py`, migration `0002`). Phase 2 code is complete; verification and the live probe are pending.

### Work completed
- Steps 1-4 remain intact and Step 4 was verified by the user locally.
- Step 5: golden Samsung battery fixture, deterministic scoring helpers, Pydantic validation and formula tests.
- Step 6: Next.js App Router, TypeScript, Tailwind, local shadcn-style UI primitives, `/api` rewrite, generated contract types, typed client, `NEXT_PUBLIC_USE_GOLDEN` switch and golden pages.
- Step 7: `docs/SCORING.md`, `docs/DESIGN_SYSTEM.md`, `docs/PHASES.md`, `docs/SERPAPI_FINDINGS.md`.
- Step 8: GitHub Actions CI with PostgreSQL migration service, backend tests/lint, golden validation, frontend typecheck/lint/test/build, and OpenAPI/type-contract checks.
- Step 9: environment/configuration scaffolding is ready with secrets kept out of the repository. Account creation itself cannot be performed from the codebase.
- Step 10: progress documentation and README updated to the actual state.

### Phase 2 work completed (2026-10-07)
- Tables `serp_cache`, `serp_usage` (migration `0002`, models, DB-backed repositories).
- `services/serpapi/`: `client` (stdlib transport, retries, error mapping, kill switch), `cache` (keys, TTL, empty TTL, pinning, purge, sanitising), `usage` (monthly counter, reserve guard, account label), `budget` (per-run cap), `estimator`, `query_planner` (lean 11-call plan), `fetcher` (cache -> guards -> client orchestration), `parsers/` (web, news, forums, YouTube, Trends), `testing` (in-memory fakes, scripted transport, `block_network`), README.
- Synthetic fixtures (6) in `tests/fixtures/serpapi/`; `scripts/record_serp_fixtures.py` (plan-only unless `--live --confirm-credits N`).
- Docs: module README, `docs/SERPAPI_FINDINGS.md` (assumptions to verify), backend README, this file.
- Phase 0/1 tests changed only where the schema head moved: table set and `0001` -> `0002` assertions.

### Phase 2 verification (see section 18 for exact status)
- 97 SerpApi-layer tests pass under a throwaway stdlib stand-in for pytest/pydantic (not part of the repo). Real pytest, Ruff, Alembic and PostgreSQL were NOT run: none were installed and the network was off.

### Verification
- Golden formula tests: 7 passed in this execution environment.
- Golden Pydantic validation is included in those tests.
- Type contract coverage: all 75 OpenAPI schemas are represented in the checked-in frontend type contract.
- Frontend npm verification: blocked here by npm registry DNS; not claimed as passed.
## 5. Milestone Progress

| Milestone | Phases | Status | Completed | Remaining |
|---|---|---|---|---|
| M1: Clickable demo | 0–1 | IMPLEMENTED | Full UI flow on golden data | Human visual check on desktop and mobile widths |
| M2: Real data pipeline | 2–6 | NOT STARTED | none | Real brand → real sentiment, aspects, signals on dashboard |
| M3: Intelligence | 7–8 | NOT STARTED | none | Investigate → cited evidence, competitor scope, recommendations |
| M4: Demo-ready | 9–10 | NOT STARTED | none | Hardened, pre-warmed, rehearsed, with fallbacks |

## 6. Implemented Architecture

| Layer | State |
|---|---|
| Browser / Next.js | Phase 1 golden journey implemented; typed client also covers estimate, usage, status, mentions (real mode untested against a backend; those endpoints are still 501 stubs) |
| FastAPI (`api/v1`) | App, health, error envelope, 11 contract stubs and schemas implemented |
| `pipeline/` | Planned for later phases |
| `services/serpapi` | Planned for Phase 2 |
| `services/processing` | Planned for Phase 3 |
| `services/nlp` | Planned for Phase 4 |
| `services/signals`, `services/scoring` | Formula primitives implemented; pipeline/scoring service later |
| `services/investigation` | Golden DTO display only; live pipeline later |
| `services/competitors` | Golden display only; real snapshots later |
| `services/recommendations` | Golden display only; generator later |
| `services/llm` | Planned for Phase 7 |
| Supabase PostgreSQL + SQLAlchemy 2 + Alembic | Local migration foundation implemented; Supabase account/connection still pending |
## 7. Frontend Status

Phase 0 baseline (still in place; Phase 1 details in 7a):

- Next.js App Router + TypeScript + Tailwind CSS.
- White/blue design tokens and local shadcn-style primitives (`Card`, `Button`, `Badge`).
- `/api/*` rewrite to FastAPI.
- Typed client backed by the OpenAPI contract.
- `NEXT_PUBLIC_USE_GOLDEN=true` switches all demo reads to the synthetic fixture.
- Landing, analyze, dashboard, investigation and evidence screens render the Samsung scenario.
- Backend-only score ownership is preserved; frontend formats values.

Phase 1 added the progress UI, error/empty/low-data/partial/quota states, responsive layouts and component tests. Still not done: manual visual check, real live API journey (backend endpoints are 501 stubs).
## 7a. Phase 1 Frontend Summary (2026-10-06)

Scope followed: `docs/PHASES.md` / `DEVELOPMENT_PLAN.md` Phase 1 (frontend on golden data). No backend, DB, API, OpenAPI, golden JSON or scoring changes. Backend/pipeline work stays in Phases 2-6.

Implemented: app shell with nav + usage indicator; landing; analyze form (category, period, competitors, estimate → confirmation dialog with remaining searches and access-code field); progress page (simulated stages in golden mode, 2 s status polling in real mode); dashboard (Brand Health with proxy-engagement mark, sentiment, aspect table with click-through drawer showing analyzed clauses/topics, search-interest SVG chart, source mix, Emerging Signal card, competitor snapshot); signal detail; investigation (steps, summary with citation links, confidence breakdown, scope badge, competitor table, recommendations, "Generated by fallback" notice); evidence explorer with original source links; competitors page.
States: skeleton (`loading.tsx`), API error (`error.tsx`), empty/no-signal, low-data, partial/warnings, quota-low/exhausted, fallback-generated report.
Frontend-only golden extras (`lib/golden/extras.ts`) supply estimate, usage, status and mentions, typed with generated OpenAPI schemas, because the golden JSON has no such sections. No new dependencies.
Tests: 21 vitest tests (`EmergingSignalCard`, `EvidenceList`, `ConfidenceBreakdown`, dialog, quota, states, golden client). Components are rendered with `react-dom/server` to avoid adding a DOM test library.
Not done: visual check against `DESIGN_SYSTEM.md` at desktop/mobile widths (needs a human with a browser); real-API mode untested; `/investigate/{signalId}` in real mode relies on `latest_investigation` (Phase 7 adds the investigate endpoint).
Verified here: backend 155 passed / 31 skipped, OpenAPI check, golden validation, type contract, ruff check + format, compileall; frontend typecheck, lint, test, build (with and without `NEXT_PUBLIC_USE_GOLDEN`), plus a `next start` smoke test returning 200 on all 8 golden routes.

## 7b. How to Run (golden demo)

```bash
cd frontend
npm ci
cp .env.example .env.local   # sets NEXT_PUBLIC_USE_GOLDEN=true
npm run dev                  # http://localhost:3000  (shortcut: /dashboard/demo)
```
Checks: `npm run typecheck`, `npm run lint`, `npm run test`, `npm run build`.
Backend (optional): `cd backend && pip install -e ".[dev]" && pytest`; `uvicorn app.main:app --reload` needs `DATABASE_URL` in `backend/.env`; only `/api/v1/health` is functional.

## 8. Backend Status

**Done:** FastAPI app, settings, logging, error envelope, `/health`, Alembic foundation, Pydantic API schemas, OpenAPI export, route contract stubs, deterministic Phase 0 scoring helpers, golden fixture validation.

**Phase 2 done:** SerpApi layer in `app/services/serpapi/` (cache, budget, usage, estimator, planner, client, fetcher, parsers) plus SerpApi repositories. `/usage` and `/analyses/estimate` stay 501 stubs: wiring them is Phase 6.

**Planned for later phases:** BackgroundTasks jobs, polling/status persistence, analysis pipeline, remaining repositories, NLP, signal detection pipeline, investigation pipeline, competitors, recommendations and Groq.
## 9. API Contract Status

OpenAPI is generated and current. The 12 documented operation IDs/paths are represented; functional business logic is intentionally deferred to later phases.

| Operation | Status |
|---|---|
| `estimateAnalysis` | Contract stub (`501`) |
| `createAnalysis` | Contract stub (`501`) |
| `listAnalyses` | Contract stub (`501`) |
| `getAnalysis` | Contract stub (`501`) |
| `getDashboard` | Contract stub (`501`) |
| `listMentions` | Contract stub (`501`) |
| `getSignal` | Contract stub (`501`) |
| `investigateSignal` | Contract stub (`501`) |
| `getInvestigation` | Contract stub (`501`) |
| `listInvestigationEvidence` | Contract stub (`501`) |
| `getUsage` | Contract stub (`501`) |
| `getHealth` | Implemented and verified |

`contracts/openapi.json` is non-empty and checked against the FastAPI export. Frontend DTO types are checked in from the OpenAPI schemas; CI also checks schema coverage.
## 10. Database Status

Design: `DATABASE.md` (v2.1). Migration order: P0 brands/analyses/analysis_brands · P2 serp_cache(+pinned), serp_usage(+account_label) · P3 content_items · P4 content_analysis, item_aspects · P5 trend_points, brand_snapshots, signals · P6 llm_calls · P7 investigations, evidence (+FKs from serp_usage/llm_calls) · P8 recommendations.

| Table | Created | Migrated | Repository | Used by pipeline | Tested |
|---|---|---|---|---|---|
| brands, analyses, analysis_brands | Yes | Yes (`0001`, local PG 16 only) | No | No | Yes (31 migration tests) |
| serp_cache, serp_usage | Yes (model + migration) | Written as `0002`, NOT yet run on PostgreSQL | Yes (`SerpCacheRepository`, `SerpUsageRepository`) | No (wired in Phase 6) | DB tests written, not run; model tests via shim only |
| content_items | No | No | No | No | No |
| content_analysis, item_aspects | No | No | No | No | No |
| trend_points, brand_snapshots, signals | No | No | No | No | No |
| llm_calls | No | No | No | No | No |
| investigations, evidence | No | No | No | No | No |
| recommendations | No | No | No | No | No |

Alembic status: set up, head = `0002` (serp_cache, serp_usage); `0001` creates all 17 enums from §3 up front, per §9 "enums" in Phase 0). Migration tests: 31 for `0001` plus 8 new for `0002` (not yet run), run against a blank throwaway PostgreSQL 16 database (skipped unless `TEST_DATABASE_URL` is set). RLS: not applied (Supabase-specific, not part of this migration). DB connectivity: `/health` returned `database: ok` on the migrated local Postgres 16; failure path verified with a refused port (no password logged). Supabase itself: NOT verified. Schema drift: none (`alembic check` and a `compare_metadata` test are clean). `pgcrypto`: not needed (`gen_random_uuid()` is built in on PG 13+).

## 11. SerpApi Status and Budget

```text
Monthly budget: 250 searches (free plan, monthly reset)
Estimated current usage: UNKNOWN — check GET /usage before the next live session.
Known remaining budget: UNKNOWN — check GET /usage before the next live session.
Reserve: 20 (SERP_MONTHLY_RESERVE guard); planning reserve ≈ 55
ALLOW_LIVE_SERPAPI: false (required default)
Cache implemented: Yes (persistent, TTL 720 h, empty 24 h, pinned entries)
Estimator implemented: Yes (service only; `/analyses/estimate` endpoint is Phase 6)
Usage endpoint: No
Account switching: new SERPAPI_API_KEY + new SERPAPI_ACCOUNT_LABEL (counter filters on label)
```

| Engine | Implemented | Fixture | Parser tested | Live behavior verified |
|---|---|---|---|---|
| Google Search (web) | Yes | Synthetic | Yes | No |
| Google News | Yes | Synthetic | Yes | No |
| Google Forums | Yes | Synthetic | Yes | No |
| YouTube Search | Yes | Synthetic | Yes | No |
| Google Trends | Yes (returns `TrendSeries`, not RawItems) | Synthetic | Yes | No |
| Google Shopping | No (optional, late) | No | No | No |
| YouTube Video | No (only if budget allows) | No | No | No |
| Search Index | Cut from MVP | — | — | — |
| Instagram Profile | Cut from MVP | — | — | — |

Credit plan (250): P2 ≤ 45 · P6 ≤ 40 · P7–8 ≤ 30 · Samsung pre-warm ≈ 20 · backup brand ≈ 20 · rehearsal/demo ≈ 40 · reserve ≈ 55. Credit log: none recorded; Phase 2 made zero live calls. `docs/SERPAPI_FINDINGS.md`: written, lists 11 UNVERIFIED assumptions for the first live session.

## 12. Fixture Status

| Fixture | Exists | Valid | Used by tests | Matches schemas | Last verified | Type |
|---|---|---|---|---|---|---|
| `contracts/golden/samsung_battery.json` | Yes | Yes | Yes | Yes | 2026-10-06 | Synthetic/golden |
| `contracts/demo/samsung_s25_ultra.json` | Empty placeholder | No | — | — | — | Demo bundle (real run, Phase 10) |
| `tests/fixtures/serpapi/*.json` (6 files) | Yes | Yes (JSON) | Yes (parser, fetcher tests) | Parsers | 2026-10-07 | SYNTHETIC mocks marked `synthetic_mock`, not recordings. Real recordings pending a live session |
| `tests/fixtures/llm/` | No | — | — | — | — | Canned LLM output |

Golden formula anchors are verified: growth `3.3×`, signal score `0.79`, health `73`, investigation confidence `86`, camera net `70`, battery net `-48`, Apple battery net `20`.
## 13. NLP Status

All **Planned**. Decided direction (do not change): local BERT-family sentiment model (start with 3-class RoBERTa such as `cardiffnlp/twitter-roberta-base-sentiment-latest`, final choice by eval in Phase 4), CPU torch, margin rule → neutral, deterministic stub for tests, rule-based relevance (brand/product/alias), clause splitting on contrast words, lexicon aspects (consumer electronics + generic), clause-level sentiment, lightweight keywords/topics, reuse by `(content_hash, analyzer_version)`. BERTopic, FAISS, sentence embeddings deferred.

Metrics: eval dataset size UNKNOWN (target 40–60) · accuracy UNKNOWN (target ≥ 75%) · macro-F1 UNKNOWN (target ≥ 0.70) · aspect recall UNKNOWN · memory UNKNOWN · cold start UNKNOWN · throughput UNKNOWN. Selected model: not chosen.

## 14. Signal Detection Status

Not implemented: window metrics, mention share, growth, guards (`n_cur ≥ 3`, `N_cur ≥ 12` growth-source items, `N_cur_all ≥ 15`), thresholds (flag ≥ 0.60, HIGH ≥ 0.75), signal score (0.35G + 0.20F + 0.25C + 0.20S), sample-size-aware confidence, Trends corroboration, Brand Health (0.35·Sentiment + 0.20·Engagement + 0.25·Risk + 0.20·Trend). Signal type for MVP: `aspect_negative_spike`; `topic_surge` reserved, not implemented. Planted battery-spike test: not written.

## 15. Investigation Status

Not implemented: pipeline, query generation, evidence collection/scoring, confidence formula (`100 × (0.30·independence + 0.25·agreement + 0.20·signal_strength + 0.15·recency + 0.10·consistency)`, cap 95, <2 independent sources → Low), citation validation, synthesis, Groq provider/limiter/fallback, idempotency, status polling.

Required behaviors, all UNVERIFIED: no evidence → inconclusive/Low; invalid evidence ID stripped; Groq quota exhausted → fallback report (`generated_by: "fallback"`); duplicate request returns existing investigation; failure → `failed` with user-safe error. Rule: confidence comes only from the formula, never from the LLM.

## 16. Competitor Status

Not implemented: competitor snapshots (current window only, news + web, max 2 competitors), comparison, aspect comparison, scope verdict (brand share ÷ median competitor share: ≥ 1.5 brand_specific, ≤ 1.2 industry_wide, between inconclusive, no data unknown), warnings. Verdict outputs verified: none of `brand_specific`, `industry_wide`, `inconclusive`, `unknown`.

## 17. Recommendation Status

Not implemented: generator, evidence linkage, priority from impact + confidence, frontend display. Every recommendation must have non-empty valid `evidence_ids` (unverified).

## 18. Testing Status

| Category | Status |
|---|---|
| Backend baseline | 155 passed, 31 skipped after Phase 0 additions (31 migration tests require TEST_DATABASE_URL) |
| Golden fixture/formulas | 7 passed in this execution environment |
| OpenAPI export/drift | Verified by user's Windows run; `openapi.json` up to date |
| Backend lint/format | Verified by user's Windows run |
| Frontend typecheck/lint/test/build | Verified in Phase 1 pass: typecheck, lint, 21 vitest tests, build (golden on/off) all pass; CI not executed |
| Frontend smoke | `next start` returned 200 on `/`, `/analyze`, `/analyze/demo`, `/dashboard/demo`, `/signals/demo-signal-battery`, `/investigate/demo-signal-battery`, `/evidence/demo-investigation`, `/competitors/demo` |
| Phase 2 SerpApi tests | 97 passed under a throwaway stdlib shim for pytest/pydantic (planner, cache, usage, budget, client, estimator, fetcher, parsers, recorder script). NOT real pytest/pydantic |
| Phase 2 DB tests | Written, never run: migration `0002` tests in `test_migrations.py`, `test_serp_repositories.py` (need `TEST_DATABASE_URL`), `test_db_models.py` additions |
| Phase 2 Ruff | NOT run (not installed). Hand-checked: line length <= 100, no unused imports (script scan), import order by eye. `ruff format --check` may still report diffs |
| Phase 0/1 regression run | NOT re-run this pass. Expect the earlier baseline plus new Phase 2 tests |
| Migration CI | Configured with PostgreSQL 16 service |

No live SerpApi/Groq calls or real NLP model loading in Phase 0 or Phase 1 tests. Phase 1 component tests use `react-dom/server` (no new test dependency).
## 19. CI/CD Status

Implemented `.github/workflows/ci.yml`:

- PostgreSQL 16 service for migration tests.
- Backend dependency install, OpenAPI check, golden validation, pytest, Ruff.
- Frontend npm install, typecheck, lint, test and production build.
- OpenAPI schema coverage check for the checked-in frontend contract.

CI has not been executed from this environment because it requires GitHub and npm network access.
## 20. Git Status

```text
Current branch: main by project instruction (ZIP contains no .git metadata)
Latest commit: unknown
Working tree clean: unknown
Commit/push: not performed by this implementation pass
```

No branch was created.
## 21. Environment / Configuration

- `backend/.env.example` contains placeholders for Supabase, SerpApi and Groq settings.
- `frontend/.env.example` enables golden mode by default and points the rewrite at local FastAPI.
- Secrets are not stored in the repository.
- `ALLOW_LIVE_SERPAPI=false` remains the required default.
- Actual Supabase/SerpApi/Groq accounts and keys are still user-owned setup and were not created or contacted here.
## 22. Known Issues

```text
Issue: Phase 2 not verified with real tooling.
Location: backend (pytest, Ruff, Alembic, PostgreSQL)
Impact: Migration 0002, SQLAlchemy models/repositories, Ruff format and the full Phase 0/1 regression run are unverified. The execution environment had no pydantic, SQLAlchemy, pytest, Ruff or PostgreSQL and no network.
Workaround: Run on a machine with dependencies: pip install -e ".[dev]"; alembic upgrade head; pytest (set TEST_DATABASE_URL); ruff check . ; ruff format --check . ; python scripts/export_openapi.py --check ; python scripts/validate_golden.py
Recommended fix: Do that before committing. Fix anything that fails (most likely candidates: ruff format diffs, migration/model drift in test_migrations.py).
```

```text
Issue: The zip's .github/workflows/ci.yml is an empty (0-byte) file, and contracts/demo/samsung_s25_ultra.json is empty.
Location: .github/workflows/ci.yml
Impact: Section 19 says CI is authored; in the uploaded copy it is not. No CI runs on push.
Workaround: Restore ci.yml from your working copy.
Recommended fix: Check git status on your side; the zip may have been exported incorrectly. Not touched in Phase 2.
```

```text
Issue: SerpApi behaviour is unverified; fixtures are synthetic.
Location: docs/SERPAPI_FINDINGS.md (11 assumptions)
Impact: Date-range encoding for News/Web/Trends, Forums result keys, billing of failed/empty calls are guesses from documentation.
Workaround: None needed for tests. 
Recommended fix: One approved live session (small probe), then update findings, planner and parsers, and record real fixtures.
```

```text
Issue: httpx is not a declared runtime dependency (pyproject lists only httpx2 under dev).
Location: backend/pyproject.toml
Impact: AGENTS.md says sync httpx for the SerpApi client, but adding dependencies needs approval. The client uses stdlib urllib behind a SerpTransport port instead.
Workaround: None needed.
Recommended fix: If you want httpx, approve it and add an HttpxTransport; nothing else changes.
```

```text
Issue: Frontend dependencies could not be installed in this execution environment.
Location: frontend/package.json / npm registry
Impact: Local frontend typecheck, lint, test and production build were not executable here.
Workaround: Run npm install in a network-enabled environment; CI performs the same checks.
Recommended fix: None in the codebase; environment/network limitation only.
```

```text
Issue: Supabase, SerpApi and Groq accounts/keys are not created yet.
Location: Phase 0 Step 9
Impact: Live database verification and later live-data phases cannot start until credentials exist.
Workaround: Golden mode works without external services.
Recommended fix: Create the accounts and place secrets only in local .env files.
```

```text
Issue: RLS is not applied.
Location: Supabase-specific setup
Impact: Supabase public access must remain blocked until RLS is enabled before exposing the database.
Workaround: Keep the database backend-only and enable RLS during Supabase setup.
Recommended fix: Add a dedicated migration after Supabase setup if the project requires schema-managed RLS.
```

```text
Issue: CI has been authored but not executed from this environment.
Location: .github/workflows/ci.yml
Impact: GitHub-specific integration remains unverified until pushed.
Workaround: The workflow includes PostgreSQL 16 and all planned checks.
Recommended fix: Run CI after the repository is pushed.
```

## 23. Important Decisions

Preserve all of these:

- Modular monolith, one monorepo, one FastAPI process, one Next.js app
- Backend is the only DB accessor; browser talks to FastAPI only
- SerpApi is the only external data provider; Groq is the only LLM provider
- 250 searches/month budget; fixture-first; persistent cache; `ALLOW_LIVE_SERPAPI=false` by default; estimate before live runs
- No live SerpApi/Groq calls and no real NLP model in normal tests
- NLP is local BERT-family + rules; Groq only for reasoning (queries, stance tagging, synthesis, recommendations, optional competitor suggestion)
- No Redis, microservices, Kubernetes, queues; BackgroundTasks + 2 s polling
- No new dependency without asking
- Backend calculates all scores; frontend only formats
- API change → update API.md, `openapi.json`, generated types, golden fixture, tests
- White-and-blue design system; red/yellow/green only for semantic status; no dark mode
- Evidence-backed claims; deterministic confidence formula; "associated with", not "caused by"
- Samsung Galaxy S25 Ultra demo, competitors Apple + OnePlus, pinned `as_of_date` 2026-08-10, `period_days` 30

Decisions made 2026-10-06 (preserve):

- Local run only, no hosting (no Docker/tunnel/HF Space)
- Max 2 competitors per analysis
- Daily cap is global (3); per-IP is rate-limit only
- SerpApi account swap via new key + `SERPAPI_ACCOUNT_LABEL`
- `serp_cache.pinned` protects demo cache from expiry/purge
- `llm_calls` migration in Phase 6; `DEMO_MODE`, alias IDs, `seed_demo.py` in Phase 6
- `serp_usage.investigation_id` and `llm_calls.investigation_id` are plain columns until Phase 7 adds FKs
- `LIVE_ACCESS_CODE` optional (empty = off)
- English only
- Hackathon MVP scope only; no scope creep

Decisions made in Phase 2 (2026-10-07, review them):

- `serp_usage.analysis_id` is ON DELETE SET NULL, not CASCADE (DATABASE.md section 8 says children cascade): deleting an analysis must not refund spent credits. `credits` limited to 0/1 and `purpose` to the 4 documented values by CHECK constraints.
- Shared types live in new `app/schemas/serp.py`; DB repositories open their own short transactions so a spent credit is never rolled back with a pipeline stage.
- Default HTTP transport is stdlib `urllib` (no new dependency); `httpx` is an optional swap behind `SerpTransport`.
- Added `fetcher.py` (cache -> guards -> client) and `sanitize.py`; service class is `ResponseCache` (not `SerpCache`, which is the DB model).
- Per-run cap counts live (credit-spending) calls only; monthly window is the UTC calendar month; reserve rule: a live call needs `remaining - 1 >= reserve`.
- "No results" responses count as 1 credit and cache for 24 h; failed calls log 0 credits.
- Trends parser returns `TrendSeries`, so "every parser returns RawItem" holds for the four content engines only.
- Competitor queries use the brand name only; plan order is priority order (competitors are dropped first when the cap is below 11).
- `scripts/probe_demo_signal.py` and `scripts/warm_demo_cache.py` NOT implemented (need a live session).

## 24. Files Changed in This Implementation Pass

```text
Backend: scoring_config.py, scripts/validate_golden.py, tests/unit/test_golden_fixture.py
Contracts: contracts/golden/samsung_battery.json
Frontend: Next.js config, TypeScript/Tailwind config, App Router pages, UI primitives, typed client, generated API types, golden fixture adapter, Vitest smoke test, frontend README
Documentation: README.md, AGENTS.md, docs/SCORING.md, docs/DESIGN_SYSTEM.md, docs/PHASES.md, docs/SERPAPI_FINDINGS.md, docs/PROGRESS.md
CI: .github/workflows/ci.yml
Scripts: scripts/check_type_contract.py
Environment: frontend/.env.example, frontend/.eslintrc.json, frontend/package.json
```
### Phase 1 pass (frontend only)

```text
New: frontend/components/{common,layout,dashboard,signals,evidence,investigation,analyze,__tests__}, frontend/lib/golden/extras.ts, frontend/lib/competitors.ts, app/dashboard/[id]/{loading,error}.tsx
Rewritten: frontend/lib/api/{client,hooks}.ts, lib/format.ts, vitest.config.ts, app/layout.tsx and all pages under app/
Tests: components/__tests__/components.test.tsx (19), lib/api/client.test.ts (+1 golden-client test; 2 total)
Docs: docs/PROGRESS.md, frontend/README.md
Unchanged (byte-identical): backend/, contracts/ (openapi.json, golden JSON), generated TS types, other docs/*.md
Incident: lib/golden/ was deleted by a cleanup command mid-pass; fixture.ts restored from the original zip, extras.ts rewritten.
```

### Phase 2 pass (SerpApi layer)

```text
New: backend/app/schemas/serp.py, app/services/serpapi/{client,cache,sanitize,usage,budget,estimator,query_planner,fetcher,testing}.py, parsers/{common,google_web,google_news,google_forums,youtube,google_trends}.py, README.md; app/db/models/serp.py, app/db/repositories/{serp_cache,serp_usage}.py; alembic/versions/20261006_0002_serp_cache_and_usage.py; scripts/record_serp_fixtures.py
Fixtures: tests/fixtures/serpapi/*.json (6, synthetic)
Tests: unit/test_serp_{cache,budget_usage,client,planner,estimator,fetcher}.py, unit/test_record_serp_fixtures.py, parsers/test_serp_parsers.py, integration/test_serp_repositories.py
Modified: app/db/models/__init__.py, tests/unit/test_db_models.py and tests/integration/test_migrations.py (table set, head 0002, new serp tests), backend/README.md, docs/SERPAPI_FINDINGS.md, docs/PROGRESS.md
Unchanged: API routes and contracts/openapi.json, golden fixture, scoring, settings, frontend, other docs
```

## 25. Next Steps

0. Verify Phase 2 on a real machine (see Known Issues, first entry), then commit on `main`.
1. Create the Supabase project and provide `DATABASE_URL` / `DATABASE_URL_DIRECT` when ready.
2. Create/provide SerpApi and Groq keys; keep `ALLOW_LIVE_SERPAPI=false` until Phase 2 live-session approval.
3. Run frontend `npm install`, `npm run generate:types`, `npm run typecheck`, `npm run lint`, `npm test`, `npm run build` locally.
4. Review and commit this Phase 0 implementation on `main`.
5. Do the manual desktop/mobile visual check against `DESIGN_SYSTEM.md`. Phase 2 is implemented; approve one small live probe to verify `docs/SERPAPI_FINDINGS.md`, then record real fixtures.
6. Repo has no commits and branch `master`; AGENTS.md says work on `main`. Create the initial commit on `main` yourself.
## 26. AI Handoff

### Current Situation
Phase 0 (contracts, backend skeleton), Phase 1 (golden frontend journey) and Phase 2 (SerpApi layer, code only) are implemented. Scope for Phase 1 followed `docs/PHASES.md`; a request to build the backend/real pipeline under the name "Phase 1" was resolved with the user as: docs Phase 1 only.

### Verified
- Backend: 155 passed / 31 skipped, OpenAPI check, golden validation, type contract (75 schemas), ruff check/format, compileall.
- Frontend: typecheck, lint, 21 tests, build, route smoke test.
- No live external services contacted; golden JSON and OpenAPI untouched.

### Pending
- Phase 2 real-tool verification (pytest, Ruff, Alembic, PostgreSQL), restoring `ci.yml`, first live probe (needs approval), real fixtures, `probe_demo_signal.py`, `warm_demo_cache.py`.
- Manual visual check (desktop + mobile) against `docs/DESIGN_SYSTEM.md`.
- External account creation/keys (Supabase, SerpApi, Groq).
- Initial commit on `main` (none exists yet).

### Exact next task
Run the Phase 2 verification list on a machine with dependencies and fix regressions. Then Phase 3 (processing and persistence: `content_items`, normalizer/dedupe/date parsing using `RawItem` from `app/schemas/serp.py`). No live calls until `ALLOW_LIVE_SERPAPI=true` is approved.

## 27. Definition of Current MVP Status

```text
MVP STATUS: PHASES 0-2 IMPLEMENTED; GOLDEN DEMO READY; PHASE 2 UNVERIFIED BY REAL TOOLING; EXTERNAL ACCOUNT SETUP PENDING
CURRENT PHASE: 2 complete at code level
CURRENT MILESTONE: M1 clickable demo, golden flow implemented (visual check pending)
NEXT REQUIRED ACTION: verify Phase 2 with real tooling, manual visual check, supply external accounts/keys, then Phase 3
```