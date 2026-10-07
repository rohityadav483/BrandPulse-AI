# BrandPulse AI — Development Progress

> **Phase 4.1 evidence (2026-10-07), read this first:** the Phase 4.1 environment had **no pytest, Ruff, pydantic, SQLAlchemy or network access** (`pip install` failed offline). So in this pass **pytest, `ruff check`, `ruff format --check`, the full backend suite, Alembic and every pre-existing test were NOT run**. What was run: the 185 new NLP tests, executed with a ~40-line stand-in for `pytest` (parametrize, raises, approx) kept outside the repo, `compileall`, an AST check for unused imports, a 100-column line-length check, and three deliberate mutations (each made the new tests fail). The new code is stdlib-only and no existing file outside docs was changed, so Phase 1-3 should be unaffected, but that is **unverified**. First action next session: `cd backend && pytest && ruff check . && ruff format --check .`, fix anything they report.
>
> **Evidence basis for the Phase 3.2 figures below (2026-10-07, Phase 3.2 pass):** the repo was inspected as an extracted zip (`BrandPulse-AI-phase2.zip`, **no `.git` directory** in the upload; local git history created in the Phase 3.1 pass). Verified by running in this pass against a local PostgreSQL 16.15: **675 backend tests passed** with `TEST_DATABASE_URL` (500 passed, 175 skipped without it; Phase 3.1 ended at 405), `ruff check` and `ruff format --check` clean (146 files), `alembic upgrade head` + `alembic check` ("No new upgrade operations detected") + `downgrade 0003` + re-upgrade on a blank database, `export_openapi.py --check`, `validate_golden.py`, `check_type_contract.py`, `compileall`, and four deliberate code mutations (each made the new tests fail). Not run: frontend (untouched), CI, Supabase, any live SerpApi/Groq call.
> Anything not listed as verified below stays **NOT STARTED** or **UNKNOWN**. **First action of any agent with repo access: inspect the repo, then correct this file.** Never assume a planned feature exists.

---

## 1. Current Status

```text
MVP STATUS: PHASES 0-3 IMPLEMENTED + PHASE 4.1 (NLP foundation) CODE-COMPLETE; NOTHING WIRED INTO ANY REAL RUN YET; GOLDEN DEMO READY; EXTERNAL ACCOUNTS PENDING
CURRENT PHASE: 4 (local NLP), step 4.1 done; 4.2 (real model, migration 0005, persistence) not started; Phase 0 external account setup still pending
CURRENT MILESTONE: M1 (Clickable demo): full golden journey implemented; manual visual check on desktop/mobile pending
OVERALL COMPLETION: Phases 0-3 implemented (Phase 0 accounts, Phase 1 visual check and Phase 2 live probe pending); Phases 4-10 not started
LAST UPDATED: 2026-10-07 (Phase 4.1)
```
## 2. Executive Summary

- **Works (verified from the user's Windows run):** backend dependencies installed, OpenAPI is current, 155 tests passed and 31 migration tests skipped without `TEST_DATABASE_URL`, Ruff check/format passed, Uvicorn started, and `/api/v1/health` returned 200.
- **Implemented in this pass:** golden Samsung fixture + formula tests, deterministic scoring helpers, Next.js/TypeScript/Tailwind frontend, typed API client with golden mode, golden dashboard → investigation → evidence flow, scoring/design docs, CI workflow, frontend/backend module READMEs, and contract coverage checks.
- **Phase 3.1 (2026-10-07):** canonical `RawItem` contract hardened, `raw_items` table (migration `0003`), `RawItemRepository`, 108 new tests; Phase 2 verified for the first time on real pytest/Ruff/PostgreSQL (see section 18).
- **Phase 3.2 (2026-10-07):** `services/processing` (cleaner, normalizer, dates, dedupe, processor), `content_items` table (migration `0004`), `ContentItemRepository`, pipeline stage `process_raw_items` (reads `raw_items`, writes `content_items`), 270 new tests. See section 4.
- **Phase 4.1 (2026-10-07):** `services/nlp` foundation: rule-based relevance, clause splitting, aspect lexicon (`config/taxonomy.py`), `SentimentAnalyzer` protocol + deterministic stub, 185 new unit tests. No model, DB, API or pipeline change. See section 4 and the verification caveat at the top of this file.
- **Not externally completed:** Supabase, SerpApi, and Groq account creation/keys. No live calls were made.
- **Frontend verification (Phase 1 pass):** npm access worked; `npm ci`, typecheck, lint, test (21 passed) and build all pass, and a `next start` smoke test returned 200 on all 8 golden routes.
- **Can it be demonstrated?** Yes. Golden mode needs only the frontend (see section 7b); no external credits are required.
## 3. Phase Progress

| Phase | Name | Status | Key Result |
|------|------|--------|------------|
| 0 | Foundations and contracts | IMPLEMENTED / EXTERNAL SETUP PENDING | Backend contracts, golden fixture, frontend golden flow, docs and CI scaffold are present |
| 1 | Frontend on golden data | IMPLEMENTED (visual check pending) | Landing → analyze (estimate + confirm dialog) → simulated progress → dashboard (health, sentiment, aspect drawer, trend, signal card) → investigation → evidence → competitors; states + 21 frontend tests |
| 2 | SerpApi layer and budget machinery | IMPLEMENTED (verified by real pytest/Ruff/PG16 on 2026-10-07; no live probe yet) | Migration `0002`, client, cache, budget/usage, estimator, planner, 5 parsers, synthetic fixtures, safe recorder script. See sections 11, 18, 22 |
| 3 | Processing and persistence | IMPLEMENTED (3.1 + 3.2; not wired into `analysis_pipeline`, verified on local PG 16 only) | **3.1:** `RawItem` contract, `raw_items` (`0003`), `RawItemRepository`. **3.2:** `cleaner`, `normalizer`, `dates`, `dedupe`, `processor`, `content_items` (`0004`), `ContentItemRepository`, stage `pipeline/process_raw_items.py` |
| 4 | Local NLP | IN PROGRESS (4.1 done, not wired) | **4.1:** `relevance`, `clauses`, `aspects` + lexicons in `config/taxonomy.py`, `SentimentAnalyzer` + stub. **Not started:** real HF analyzer, `model_loader`, keywords/topics, migration `0005`, repositories, eval, reuse by `analyzer_version`, pipeline wiring |
| 5 | Signals, scoring and brand health | NOT STARTED | Formula primitives only; pipeline not implemented |
| 6 | Analysis pipeline and first real end-to-end | NOT STARTED | — |
| 7 | Groq and investigation | NOT STARTED | Golden report only; live investigation not implemented |
| 8 | Competitors and recommendations | NOT STARTED | Golden display only |
| 9 | Hardening and testing | NOT STARTED | — |
| 10 | Demo bundle, pre-warm, polish and rehearsal | NOT STARTED | — |
## 4. Current Phase

### Goal
Phase 3.2: normalization, dates, deduplication and `content_items` (builds on the Phase 3.1 `raw_items` store). Next is Phase 4 (local NLP); nothing from Phase 4 or later was started.

### Current module
`backend/app/services/processing/` (+ `app/schemas/processing.py`, `app/db/models/content_item.py`, `app/db/repositories/content_item.py`, `app/pipeline/process_raw_items.py`, migration `0004`). Phase 3.1 code (`RawItem`, `raw_items`, `RawItemRepository`) is unchanged.

### Work completed
- Steps 1-4 remain intact and Step 4 was verified by the user locally.
- Step 5: golden Samsung battery fixture, deterministic scoring helpers, Pydantic validation and formula tests.
- Step 6: Next.js App Router, TypeScript, Tailwind, local shadcn-style UI primitives, `/api` rewrite, generated contract types, typed client, `NEXT_PUBLIC_USE_GOLDEN` switch and golden pages.
- Step 7: `docs/SCORING.md`, `docs/DESIGN_SYSTEM.md`, `docs/PHASES.md`, `docs/SERPAPI_FINDINGS.md`.
- Step 8: GitHub Actions CI with PostgreSQL migration service, backend tests/lint, golden validation, frontend typecheck/lint/test/build, and OpenAPI/type-contract checks.
- Step 9: environment/configuration scaffolding is ready with secrets kept out of the repository. Account creation itself cannot be performed from the codebase.
- Step 10: progress documentation and README updated to the actual state.

### Phase 4.1 work completed (2026-10-07)
- Scope: **Phase 4.1 only** (NLP foundation). Phase 4.2 was not started.
- `services/nlp/relevance.py`: `BrandProfile(brand, products, aliases)`, `detect_relevance` -> `RelevanceResult(is_about_brand, matched_terms, in_title, in_snippet)`; whole-word, case/punctuation-insensitive; nothing derived (aliases must be configured).
- `services/nlp/clauses.py`: `split_clauses` -> `Clause(text, index, sentence_index)`; sentence split (terminators, ellipsis, `;`, newline; not inside numbers or after `vs.`/`e.g.`), then split on `but`, `however`, `although`, `though`, `even though`, `whereas`, `nevertheless`, `nonetheless`, `on the other hand`, plus `while`/`yet` only after a comma; contrast word dropped; `but also`, `nothing but` etc. not split.
- `config/taxonomy.py` (was an empty file): aspect lexicons `consumer_electronics` (battery, charging, camera, display, performance, price, design, software, customer_support, audio, connectivity) and `generic`, read-only, `get_lexicon`, `LEXICON_VERSION = "lex-1"`. `services/nlp/aspects.py`: `detect_aspects`, `detect_aspects_in_text`, `terms_in_text`, `aspect_names`; one clause per aspect (PK `(content_id, aspect)`).
- `services/nlp/sentiment.py`: `SentimentAnalyzer` (runtime-checkable Protocol: `model_name`, `analyze(texts)`), `SentimentResult` (three probabilities, `.score`), `StubSentimentAnalyzer` (keyword counts + negation window, `stub-lexicon-v1`). `services/nlp/textnorm.py`: local `normalize_text` (services must not import `processing`).
- Tests (all pure, no DB): `test_nlp_relevance.py`, `test_nlp_clauses.py`, `test_nlp_aspects.py` (includes lexicon well-formedness), `test_nlp_sentiment.py`, `test_nlp_foundation.py` (PRD case "camera amazing but battery terrible" -> camera positive, battery negative with the stub; import-layering and no-torch guards). 185 cases.
- Docs: `services/nlp/README.md` (new), `backend/README.md`, this file.
- Decisions to confirm: (1) value types are frozen **stdlib dataclasses**, not Pydantic, because nothing crosses an API/DB boundary yet and Pydantic was not installable here; 4.2 can wrap them. (2) Bare `update`, `slow`, `fast`, `support` are not aspect terms (too ambiguous alone), so e.g. "since the update" alone does not create a software aspect. (3) Aspect names `price` and `customer_support` (plan text says "pricing" / "customer support"). (4) `ARCHITECTURE.md` lists `taxonomy.py` under `config/`; lexicons were put there as designed.
- NOT done on purpose: real BERT/RoBERTa analyzer, `model_loader`, `keywords`, `topics`, migration `0005`, `content_analysis`/`item_aspects`, repositories, pipeline integration, API/OpenAPI changes, SerpApi, Groq, frontend, new dependencies, eval set.

### Phase 2 work completed (2026-10-07)
- Tables `serp_cache`, `serp_usage` (migration `0002`, models, DB-backed repositories).
- `services/serpapi/`: `client` (stdlib transport, retries, error mapping, kill switch), `cache` (keys, TTL, empty TTL, pinning, purge, sanitising), `usage` (monthly counter, reserve guard, account label), `budget` (per-run cap), `estimator`, `query_planner` (lean 11-call plan), `fetcher` (cache -> guards -> client orchestration), `parsers/` (web, news, forums, YouTube, Trends), `testing` (in-memory fakes, scripted transport, `block_network`), README.
- Synthetic fixtures (6) in `tests/fixtures/serpapi/`; `scripts/record_serp_fixtures.py` (plan-only unless `--live --confirm-credits N`).
- Docs: module README, `docs/SERPAPI_FINDINGS.md` (assumptions to verify), backend README, this file.
- Phase 0/1 tests changed only where the schema head moved: table set and `0001` -> `0002` assertions.

### Phase 3.1 work completed (2026-10-07)
- `RawItem` (`app/schemas/serp.py`) is now the validated canonical contract: engine must be a content engine (Trends rejected), `source_type` must match `ENGINE_SOURCE_TYPE[engine]`, `title`/`url` not blank, `position >= 1`; values are never modified. New `compute_raw_key()` (sha256 over verbatim identifying fields; idempotency key, not dedupe). New `RawItemContext` (analysis, brand, purpose, window; collection needs a window, investigation has none), `StoredRawItem`, `RawItemWriteResult`.
- Table `raw_items` (migration `0003`, model `RawItemRow`): verbatim item fields, `published_raw`/`published_iso` kept as strings, `metadata` jsonb, `serp_cache_key` (no FK), `raw_key`, `collected_at`. Unique index `(analysis_id, brand_id, purpose, raw_key)`; indexes `(analysis_id, brand_id, window)`, `(analysis_id, source_type)`, `(serp_cache_key)`; six check constraints; FK `analysis_id` CASCADE, `brand_id` no cascade. Reuses enums from `0001`.
- `RawItemRepository`: `add`, `add_many` (one transaction, `ON CONFLICT DO NOTHING`, returns inserted/duplicate counts), `get`, `list_for_analysis` (filters, stable order, paging), `count`, `exists`, `existing_keys`.
- Python enum mirrors added: `ContentPurpose` (domain), `SourceType`/`WindowKind`/`ContentPurpose` (DB models), with parity tests against `docs/DATABASE.md`.
- Docs: `docs/DATABASE.md` 5.4a + migration plan + lifecycle rows, serpapi README, backend README, this file.
- NOT done on purpose (Phase 3.2): cleaning, canonical URL, `url_hash`/`content_hash`/`dup_group`, date parsing, window assignment, dedupe, `content_items`. No pipeline wiring (Phase 6). No API/OpenAPI change.

### Phase 3.2 work completed (2026-10-07)
- `services/processing/` (README inside): `cleaner.clean_text`; `normalizer` (`canonical_url`, `extract_domain`, `url_hash`, `content_hash`, `normalize_for_match`, `title_key`); `dates` (`parse_published` -> `exact`/`approximate`/`unknown`, `window_for_date`, `assign_window`); `dedupe` (exact duplicates by `content_hash` or canonical `url_hash`, transitive, best-quality kept; near-duplicate `dup_group` by identical normalized title or token Jaccard >= 0.8 with >= 4 words, no chaining, no embeddings); new `processor.process_raw_items` composing them for one (analysis, brand) batch. **`cleaner.py`, `dates.py`, `normalizer.py` were not written in this pass: see "Provenance" below.**
- `schemas/processing.py`: `ContentItem`, `StoredContentItem`, `ContentWriteResult`, `DropReason`, `DroppedRaw`, `ProcessingStats`, `ProcessingOutcome`, `ProcessingRunResult`. Reuses `StoredRawItem`/`RawItem`; no SerpApi data was re-fetched or re-parsed.
- Table `content_items` (migration `0004`, model `ContentItemRow`): exactly the DATABASE.md 5.5 columns, no extra columns. Unique index `(analysis_id, brand_id, content_hash)`; indexes `(analysis_id, brand_id, window)`, `(analysis_id, source_type)`, `(content_hash)` as documented, plus `(analysis_id, brand_id, url_hash)` and `(analysis_id, dup_group)`; nine check constraints; FK `analysis_id` CASCADE, `brand_id` no cascade. Reuses enums from `0001`.
- `ContentItemRepository`: `add`, `add_many` (one transaction, `ON CONFLICT DO NOTHING`), `get`, `list_for_analysis`, `count`, `count_dup_groups`, `existing_content_hashes`, `existing_url_hashes`, `stored_hashes`.
- Stage `pipeline/process_raw_items.py::process_analysis_raw_items`: reads `raw_items` (filters: brand, purpose), processes per brand with already-stored hashes as `known_*`, writes `content_items`, returns `ProcessingRunResult`. Idempotent; never touches SerpApi; not yet called from `analysis_pipeline` (Phase 6).
- Python enum mirror `DateConfidence` added to `db/models/enums.py`.
- Docs: `services/processing/README.md` (new), `docs/DATABASE.md` (5.5 implementation notes, migration plan), `backend/README.md`, this file.
- NOT done on purpose: NLP, relevance, scoring, signals, Groq, API/OpenAPI changes, wiring into `analysis_pipeline`, a service to pull `serp_cache.fetched_at` for `reference_times` (the parameter exists; the caller wiring is Phase 6).

### Provenance of three processing files (read this)
When this pass began, `services/processing/cleaner.py`, `dates.py` and `normalizer.py` already contained full implementations in the working tree as **uncommitted modifications**; the Phase 3.1 commit had them as empty files. I did not write them and cannot say who did. I read them, smoke-tested them, wrote tests for them (`test_processing_cleaner_normalizer.py` 72, `test_processing_dates.py` 73: all pass, no defects found) and committed them unchanged (md5 and mtime identical before and after my edits) as part of the Phase 3.2 commit, because they match the requested spec. If they came from somewhere you did not expect, review them before relying on this pass; everything else in Phase 3.2 (`dedupe.py`, `processor.py`, schemas, model, migration, repository, pipeline stage, all other tests and docs) was written here.

### Phase 2 verification (updated 2026-10-07)
- Verified in the Phase 3.1 pass on real tooling (pytest 9.1.1, pydantic 2.13.5, SQLAlchemy 2.0.54, Alembic 1.20.0, Ruff 0.16.10, PostgreSQL 16.15): all 297 tests passed before any change, including the Phase 2 migration and repository DB tests; `ruff check` clean. `ruff format --check` reported one diff in `tests/unit/test_serp_client.py`, now reformatted (formatting only). The earlier "97 tests under a shim" evidence is superseded.

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
| `pipeline/` | `process_raw_items.py` stage implemented (Phase 3.2); `analysis_pipeline`, `investigation_pipeline`, `jobs` still empty stubs (Phase 6) |
| `services/serpapi` | Planned for Phase 2 |
| `services/processing` | Implemented (Phase 3.2): cleaner, normalizer, dates, dedupe, processor. `pipeline/process_raw_items.py` wires it to the repositories; not yet called by `analysis_pipeline` |
| `services/nlp` | Phase 4.1 implemented: `relevance`, `clauses`, `aspects`, `sentiment` (protocol + stub), `textnorm`; lexicons in `config/taxonomy.py`. `model_loader`, `keywords`, `topics` still empty. Not called by any pipeline |
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

**Phase 3.1 done:** validated `RawItem` contract, `raw_items` model/migration, `RawItemRepository` (not yet wired into any pipeline; nothing calls it outside tests).

**Phase 3.2 done:** processing services, `content_items` model/migration, `ContentItemRepository`, `process_raw_items` pipeline stage (only exercised by tests; nothing in the API calls it).

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

Design: `DATABASE.md` (v2.1). Migration order: P0 brands/analyses/analysis_brands · P2 serp_cache(+pinned), serp_usage(+account_label) · P3.1 raw_items (`0003`) · P3.2 content_items (`0004`) · P4 content_analysis, item_aspects · P5 trend_points, brand_snapshots, signals · P6 llm_calls · P7 investigations, evidence (+FKs from serp_usage/llm_calls) · P8 recommendations.

| Table | Created | Migrated | Repository | Used by pipeline | Tested |
|---|---|---|---|---|---|
| brands, analyses, analysis_brands | Yes | Yes (`0001`, local PG 16 only) | No | No | Yes (31 migration tests) |
| serp_cache, serp_usage | Yes | Yes (`0002`, local PG 16 only) | Yes (`SerpCacheRepository`, `SerpUsageRepository`) | No (wired in Phase 6) | Yes (DB tests ran and passed 2026-10-07) |
| raw_items | Yes (model + migration) | Yes (`0003`, local PG 16 only) | Yes (`RawItemRepository`) | No (wired in Phase 6) | Yes (35 added migration tests (74 total in file, was 39) + 23 repository tests + 46 schema tests) |
| content_items | Yes (model + migration) | Yes (`0004`, local PG 16 only) | Yes (`ContentItemRepository`) | Stage `process_raw_items` exists; not called by `analysis_pipeline` yet (Phase 6) | Yes (49 added migration tests + 15 repository + 11 pipeline-stage DB tests; 194 pure unit tests for processing) |
| content_analysis, item_aspects | No | No | No | No | No |
| trend_points, brand_snapshots, signals | No | No | No | No | No |
| llm_calls | No | No | No | No | No |
| investigations, evidence | No | No | No | No | No |
| recommendations | No | No | No | No | No |

Alembic status: set up, head = `0004` (content_items); `0003` = raw_items; `0002` = serp_cache, serp_usage; `0001` creates all 17 enums from §3 up front, per §9 "enums" in Phase 0. Migration tests (123 in `test_migrations.py`, covering `0001`-`0004`, upgrade, downgrade to `0003`/`0002`/`0001`/base, drift check), run against a blank throwaway PostgreSQL 16 database (skipped unless `TEST_DATABASE_URL` is set). RLS: not applied (Supabase-specific, not part of this migration). DB connectivity: `/health` returned `database: ok` on the migrated local Postgres 16; failure path verified with a refused port (no password logged). Supabase itself: NOT verified. Schema drift: none (`alembic check` and a `compare_metadata` test are clean). `pgcrypto`: not needed (`gen_random_uuid()` is built in on PG 13+).

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

**Phase 4.1 implemented (not wired, no model):** rule-based relevance, clause splitting, aspect lexicons, `SentimentAnalyzer` protocol and deterministic stub (section 4). **Everything else below is still Planned.** Decided direction (do not change): local BERT-family sentiment model (start with 3-class RoBERTa such as `cardiffnlp/twitter-roberta-base-sentiment-latest`, final choice by eval in Phase 4), CPU torch, margin rule → neutral, deterministic stub for tests, rule-based relevance (brand/product/alias), clause splitting on contrast words, lexicon aspects (consumer electronics + generic), clause-level sentiment, lightweight keywords/topics, reuse by `(content_hash, analyzer_version)`. BERTopic, FAISS, sentence embeddings deferred.

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
| Backend full suite (2026-10-07) | **675 passed** with `TEST_DATABASE_URL` against local PostgreSQL 16.15; **500 passed, 175 skipped** without it. Same suite: 297 passed before Phase 3.1, 405 after it. Includes Phase 0, 1 (backend part), 2, 3.1 and 3.2 |
| Golden fixture/formulas | 7 passed in this execution environment |
| OpenAPI export/drift | Verified by user's Windows run; `openapi.json` up to date |
| Backend lint/format | Verified by user's Windows run |
| Frontend typecheck/lint/test/build | Verified in Phase 1 pass: typecheck, lint, 21 vitest tests, build (golden on/off) all pass; CI not executed |
| Frontend smoke | `next start` returned 200 on `/`, `/analyze`, `/analyze/demo`, `/dashboard/demo`, `/signals/demo-signal-battery`, `/investigate/demo-signal-battery`, `/evidence/demo-investigation`, `/competitors/demo` |
| Phase 2 tests | Passed on real tooling (297 before Phase 3.1 changes), including `0002` migration tests and `test_serp_repositories.py` on PostgreSQL |
| Phase 3.1 tests | `unit/test_raw_item_schema.py` (46: contract validation, raw_key, context rules, all four engine fixtures), `integration/test_raw_item_repository.py` (23, PostgreSQL: lossless round trip of every engine fixture, idempotency, filters, exists, atomic batch, cascade), `0003` additions in `test_migrations.py` (columns, defaults, indexes, FKs, every check constraint, downgrade paths). A mutation check (repository dropping `published_raw`) made the round-trip test fail, as it should |
| Phase 3.2 tests | Unit (no DB): `test_processing_cleaner_normalizer.py` (72), `test_processing_dates.py` (73), `test_processing_dedupe.py` (20), `test_processing_processor.py` (29). PostgreSQL: `test_content_item_repository.py` (15), `test_process_raw_items_pipeline.py` (11), `0004` additions in `test_migrations.py` (columns, defaults, indexes, FKs/cascade, every check constraint, downgrade to `0003`/`0002`). All use the synthetic SerpApi fixtures (14 content items across web, news, forums, YouTube) plus inline synthetic items for duplicates, syndication, bad URLs/titles. Four mutations (near-duplicate threshold, ignoring URL hash, ignoring dates for windows, pipeline ignoring stored hashes) each failed the tests, as they should |
| Phase 4.1 tests | 185 cases in 5 files (`unit/test_nlp_*.py`), no DB. **Run only with a local pytest stand-in, not real pytest** (see top of file): 185 run, 0 failed. Mutations (dropped `but also` guard, tie-break `>` to `>=`, negation window 2 to 0) failed 1, 1 and 5 cases respectively, then restored. Real pytest, Ruff check/format, the full suite (675 / 500+175 as of Phase 3.2), OpenAPI/golden/type-contract checks and Alembic were **not run** in this pass |
| Backend lint/format (2026-10-07) | `ruff check .` clean; `ruff format --check .` clean (146 files) |
| Other checks (2026-10-07) | `export_openapi.py --check` up to date; `validate_golden.py` ok; `check_type_contract.py` ok (75 schemas); `compileall` ok; `alembic upgrade head`, `alembic check`, `downgrade 0003`, re-upgrade ok on a blank DB |
| Frontend (this pass) | Not touched, not re-run |
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
Current branch: main (no other branch exists or was created)
History: the original upload had no .git; the Phase 3.1 pass ran `git init -b main`. Local commits so far (commit 4 added in the Phase 4.1 pass):
  1. "Baseline: Phases 0-2 as uploaded" (the zip exactly as received)
  2. "Phase 3.1: RawItem contract and persistence"
  3. "Phase 3.2: normalization, dates, deduplication and content_items"
  4. "Phase 4.1: NLP foundation (relevance, clauses, aspects, SentimentAnalyzer + stub)"
This history is local to the returned zip and is NOT connected to your own repository's history. If you already have commits, apply commits 2-4 as patches (`git format-patch -3`) instead of adopting this .git.
Push/tag: not performed
```
## 21. Environment / Configuration

- `backend/.env.example` contains placeholders for Supabase, SerpApi and Groq settings.
- `frontend/.env.example` enables golden mode by default and points the rewrite at local FastAPI.
- Secrets are not stored in the repository.
- `ALLOW_LIVE_SERPAPI=false` remains the required default.
- Actual Supabase/SerpApi/Groq accounts and keys are still user-owned setup and were not created or contacted here.
## 22. Known Issues

```text
Issue: Phase 4.1 was not verified with real pytest or Ruff.
Location: backend/tests/unit/test_nlp_*.py, backend/app/services/nlp/, backend/app/config/taxonomy.py
Impact: The environment had no pytest, Ruff, pydantic, SQLAlchemy or network. The 185 new tests passed only under a local stand-in runner; `ruff check` / `ruff format --check` never ran (format diffs are possible, e.g. in the one-per-line word sets), and the pre-existing suite was not re-run.
Workaround: None needed to read the code.
Recommended fix: Run `cd backend && pytest && ruff check . && ruff format --check .` (with TEST_DATABASE_URL for the DB tests) before starting Phase 4.2; fix whatever they report and update section 18.
```

```text
Issue: (RESOLVED 2026-10-07) Phase 2 was unverified with real tooling.
Resolution: the Phase 3.1 pass ran pytest, Ruff, Alembic and PostgreSQL 16 on the Phase 2 code before changing anything: 297 passed, ruff check clean, migration 0002 applied. One formatting diff in tests/unit/test_serp_client.py was fixed.
Still unverified: Supabase itself, CI, frontend in this pass.
```

```text
Issue: Three processing files appeared as uncommitted changes before the Phase 3.2 pass.
Location: backend/app/services/processing/{cleaner,dates,normalizer}.py
Impact: Their author is unknown to this pass (see "Provenance" in section 4). They were tested and committed unchanged.
Workaround: None needed if you wrote them or approve them.
Recommended fix: Review them once; they have 145 tests.
```

```text
Issue: Relative dates are measured from raw_items.collected_at unless the caller passes reference_times.
Location: pipeline/process_raw_items.py (parameter exists; nothing supplies it yet)
Impact: For results persisted later than SerpApi was called, "3 weeks ago" is anchored a little late. Phase 6 should pass serp_cache.fetched_at per serp_cache_key.
Workaround: Pass reference_times from SerpCacheRepository.get(key).fetched_at.
Recommended fix: Do it when wiring Phase 6.
```

```text
Issue: Near-duplicate grouping only sees the batch being processed.
Location: services/processing/dedupe.py
Impact: Items stored in an earlier run (e.g. collection) are not fuzzy-matched against investigation items added later; only an identical normalized title joins the same dup_group via its hash.
Workaround: None needed for the collection stage.
Recommended fix: Decide in Phase 7 whether investigation needs title tokens of stored items.
```

```text
Issue: Date, canonical-URL and dedupe behavior is verified on synthetic fixtures only.
Location: tests/fixtures/serpapi/ (synthetic_mock), docs/SERPAPI_FINDINGS.md
Impact: Real SerpApi date strings, URL shapes and syndication patterns may differ.
Workaround: None.
Recommended fix: Re-run the processing tests against recorded fixtures after the first approved live session.
```

```text
Issue: The zip's .github/workflows/ci.yml is an empty (0-byte) file, and contracts/demo/samsung_s25_ultra.json is empty.
Location: .github/workflows/ci.yml
Impact: Section 19 says CI is authored; in the uploaded copy it is not (still 0 bytes after Phase 3.1; not touched). No CI runs on push.
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

Decisions made in Phase 3.1 (2026-10-07, review them):

- **Added a `raw_items` table that DATABASE.md did not have.** The docs go straight from `serp_cache` to `content_items` (normalized). The request asked for persisted RawItems, so `raw_items` is an additive staging table; `content_items` stays Phase 3.2. DATABASE.md 5.4a, the migration plan and the lifecycle table were updated; no existing design was changed. If you would rather have no staging table, drop migration `0003` and persist only `content_items`.
- `raw_key` (sha256 of verbatim engine, source type, query, cache key, position, URL, title, snippet, dates) is an idempotency key only. Exact repeats are skipped, the same article from two queries stays two rows. No normalization, so Phase 3.2 owns every dedupe decision.
- `url_hash`, `content_hash`, `dup_group` are not in `raw_items`: they are normalization outputs and belong to `content_items`.
- `published_raw` and `published_iso` are text, not timestamptz, so nothing is parsed or guessed before 3.2.
- `serp_cache_key` has no foreign key because `serp_cache` rows expire and are purged.
- `purpose = collection` requires a window and `investigation` forbids one (DATABASE.md 5.5 says window is null for investigation items; requiring it for collection is the stricter reading) as a CHECK, mirrored in `RawItemContext`.
- `RawItem` validation is stricter than in Phase 2 (engine/source_type match, no Trends, non-blank title/url, `position >= 1`). All Phase 2 parsers and fixtures still pass unchanged.
- Blank check uses `~ '\S'`, not `btrim`: the tests showed Postgres `btrim` ignores tabs and newlines while Pydantic's `strip()` does not.
- `RawItemRepository` follows the SerpApi repositories: takes an `Engine`, one short transaction per call. Pipeline stage transactions can change that in Phase 6 if needed.
- Added `ContentPurpose` to `schemas/domain.py`; mirrored `SourceType`, `WindowKind`, `ContentPurpose` in `db/models/enums.py`.

Decisions made in Phase 3.2 (2026-10-07, review them):

- `content_items` matches DATABASE.md 5.5 column for column. No `raw_item_id` column was added: traceability uses `serp_cache_key`, and dropped duplicates are reported in `ProcessingRunResult.dropped` (raw item id + reason), not persisted.
- `content_items.window` is nullable and also null for collection items whose known date is outside both windows (kept, counted in no window). Undated items keep the window of the call that found them. Investigation items always have no window (check constraint).
- Exact duplicate = same `content_hash` OR same canonical `url_hash`, within (analysis, brand), transitively. DATABASE.md only specifies the `content_hash` unique index; URL-level dedupe is enforced in code plus a non-unique `(analysis_id, brand_id, url_hash)` index, because the same page returned with a different snippet is still the same source.
- The unique index ignores `purpose` (as DATABASE.md says), so an investigation item identical to a collected one is skipped as `already_stored`; evidence will link to the existing content item.
- Near-duplicate rule: normalized title equal, or both titles >= 4 words and token Jaccard >= 0.8 against the first item of a group (no chaining). Conservative on purpose; thresholds are constants in `dedupe.py`.
- `dup_group` = sha256 of the normalized title (outlet suffix stripped only when it equals the author); punctuation-only titles fall back to a URL-based group so they never merge.
- Added `services/processing/processor.py` (pure `RawItem -> ContentItem` composition) next to the four modules named in ARCHITECTURE.md so the pipeline stage stays thin and the logic is testable without a DB. `ARCHITECTURE.md` itself was not changed.
- Domain is the canonical host without presentation prefixes, not a registered domain (no public-suffix list, no new dependency).
- `content_items.query` NOT NULL: a raw item without a query stores `''`.
- Pipeline stage processes one brand at a time (the unique index scope) and passes already-stored hashes into dedupe, which is what makes re-runs idempotent.
- New shared integration fixtures in `tests/integration/conftest.py`; older integration files keep their own copies. Factories added to `tests/conftest.py`.

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

### Phase 3.1 pass (RawItem contract and persistence)

```text
New: backend/alembic/versions/20261007_0003_raw_items.py, backend/app/db/models/raw_item.py, backend/app/db/repositories/raw_item.py
New tests: tests/unit/test_raw_item_schema.py, tests/integration/test_raw_item_repository.py
Modified: app/schemas/serp.py (RawItem validation + compute_raw_key, RawItemContext, StoredRawItem, RawItemWriteResult), app/schemas/domain.py (ContentPurpose), app/db/models/enums.py, app/db/models/__init__.py
Modified tests: tests/integration/test_migrations.py (head 0003, raw_items tests, downgrade paths), tests/unit/test_db_models.py (table set), tests/unit/test_domain.py (enum parity), tests/unit/test_serp_client.py (ruff format only)
Docs: docs/DATABASE.md (5.4a, migration plan, lifecycle), backend/README.md, backend/app/services/serpapi/README.md, docs/PROGRESS.md
Unchanged: API routes, contracts/openapi.json, golden fixture, scoring, settings, frontend, parsers, fixtures, ARCHITECTURE.md and other docs, ci.yml (still empty)
```

### Phase 3.2 pass (processing and content_items)

```text
New: backend/alembic/versions/20261007_0004_content_items.py, backend/app/db/models/content_item.py, backend/app/db/repositories/content_item.py, backend/app/pipeline/process_raw_items.py, backend/app/schemas/processing.py, backend/app/services/processing/{dedupe,processor}.py (dedupe.py was an empty file), backend/app/services/processing/README.md
Pre-existing uncommitted, committed unchanged (not written in this pass): backend/app/services/processing/{cleaner,dates,normalizer}.py
New tests: tests/unit/test_processing_{cleaner_normalizer,dates,dedupe,processor}.py, tests/integration/{conftest,test_content_item_repository,test_process_raw_items_pipeline}.py
Modified: app/db/models/__init__.py (ContentItemRow), app/db/models/enums.py (DateConfidence)
Modified tests: tests/integration/test_migrations.py (head 0004, content_items tests, downgrade paths), tests/unit/test_db_models.py (table set, offline-SQL assertion), tests/unit/test_domain.py (DateConfidence parity), tests/conftest.py (StoredRawItem factories)
Docs: docs/DATABASE.md (5.5 implementation notes, migration plan), backend/README.md, docs/PROGRESS.md
Unchanged: Phase 3.1 code, API routes, contracts/openapi.json, golden fixture, scoring, settings, frontend, parsers, fixtures, ARCHITECTURE.md and other docs, ci.yml (still empty)
```

## 25. Next Steps

0. Phases 2, 3.1 and 3.2 verified locally (section 18). Review the three pre-existing processing files (section 4, Provenance). Reconcile the returned git history with your own repo (section 20).
1. Create the Supabase project and provide `DATABASE_URL` / `DATABASE_URL_DIRECT` when ready.
2. Create/provide SerpApi and Groq keys; keep `ALLOW_LIVE_SERPAPI=false` until Phase 2 live-session approval.
3. Run frontend `npm install`, `npm run generate:types`, `npm run typecheck`, `npm run lint`, `npm test`, `npm run build` locally.
4. Review and commit this Phase 0 implementation on `main`.
5. Do the manual desktop/mobile visual check against `DESIGN_SYSTEM.md`. Phases 2 and 3 are implemented; approve one small live probe to verify `docs/SERPAPI_FINDINGS.md`, then record real fixtures.
6. Repo has no commits and branch `master`; AGENTS.md says work on `main`. Create the initial commit on `main` yourself.
## 26. AI Handoff

### Current Situation
Phase 0 (contracts, backend skeleton), Phase 1 (golden frontend journey), Phase 2 (SerpApi layer, code only) and Phase 3 (3.1 RawItem + `raw_items`, 3.2 processing + `content_items`) are implemented. Scope for Phase 1 followed `docs/PHASES.md`; a request to build the backend/real pipeline under the name "Phase 1" was resolved with the user as: docs Phase 1 only.

### Verified
- Backend: 155 passed / 31 skipped, OpenAPI check, golden validation, type contract (75 schemas), ruff check/format, compileall.
- Frontend: typecheck, lint, 21 tests, build, route smoke test.
- No live external services contacted; golden JSON and OpenAPI untouched.

### Pending
- Restoring `ci.yml` (empty in the zip), first live probe (needs approval), real fixtures, `probe_demo_signal.py`, `warm_demo_cache.py`.
- Manual visual check (desktop + mobile) against `docs/DESIGN_SYSTEM.md`.
- External account creation/keys (Supabase, SerpApi, Groq).
- Reconcile the git history in the returned zip with your own repository (section 20).

### Exact next task
Phase 4 (local NLP, `docs/DEVELOPMENT_PLAN.md`): relevance rule, clause splitting, aspect lexicon, `SentimentAnalyzer` interface + deterministic stub, then `content_analysis` / `item_aspects` migration (`0005`) keyed by `(content_hash, analyzer_version)`. Input is `StoredContentItem` from `app/schemas/processing.py`; `content_items.content_hash` is already the reuse key. Do not load the real model in default tests. Before Phase 6 wiring, supply `reference_times` from `serp_cache.fetched_at` (section 22). No live calls until `ALLOW_LIVE_SERPAPI=true` is approved.

## 27. Definition of Current MVP Status

```text
MVP STATUS: PHASES 0-3 IMPLEMENTED AND BACKEND-VERIFIED LOCALLY (NOT WIRED INTO A REAL RUN); EXTERNAL ACCOUNT SETUP PENDING
CURRENT PHASE: 3 complete at code level; 4 next
CURRENT MILESTONE: M1 clickable demo, golden flow implemented (visual check pending)
NEXT REQUIRED ACTION: review the three pre-existing processing files; Phase 4 (local NLP); manual visual check; supply external accounts/keys
```