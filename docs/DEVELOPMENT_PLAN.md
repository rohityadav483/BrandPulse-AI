# BrandPulse AI: Development Plan (v2)

Companion documents: `ARCHITECTURE.md`, `DATABASE.md`, `API.md`, and `docs/SCORING.md` (written in Phase 0).

Stack: Next.js + TypeScript + Tailwind + shadcn/ui · FastAPI · Supabase PostgreSQL · SerpApi (free plan, 250 searches/month) · Groq (free tier) · local BERT-family NLP. Runs locally only (hackathon MVP, no hosting). Built with AI-assisted coding (Claude for planning and review, Antigravity as coding agent, GitHub for version control).

Sizes are relative effort: **S** small, **M** medium, **L** large.

**What changed from v1:** local BERT NLP replaces LLM-based NLP (Phase 4); Groq arrives in Phase 7; SerpApi is budgeted to 250 searches/month, which changes how every phase is run; the demo is a pinned-date Samsung scenario.

---

## 1. Working agreement

### How to work with the coding agent
- **One phase, one module per prompt.** Never ask for the whole app.
- Start every prompt with: phase goal, module path, relevant section of `API.md` / `DATABASE.md`, and "follow AGENTS.md".
- Give the agent a fixture (golden JSON, recorded SerpApi JSON, canned LLM JSON, stub analyzer) so it never needs live services or the real model.
- Ask for tests in the same prompt as the code.
- Review diffs. Reject new dependencies and out-of-module changes unless justified.
- If the agent breaks something, revert to the last green commit and re-prompt with a smaller scope.

### Prompt template
```text
Phase <N>, module <path>.
Goal: <one sentence>.
Read first: AGENTS.md, <module README>, <doc section>, <fixture path>.
Inputs/outputs: <Pydantic types>.
Constraints: no new dependencies; no live SerpApi or Groq calls; do not load the real NLP model
in unit tests (use the stub); logic stays pure.
Deliver: code + tests in <tests path>. Run tests and report results.
```

### Credit discipline (free tier)
- `ALLOW_LIVE_SERPAPI=false` in `.env` by default. Turn it on only for a planned live session, then off again.
- Every live session has a written budget (see §3) and a purpose. Log what you learned in `docs/SERPAPI_FINDINGS.md`.
- Always run the estimator first. Never retry a failed live run blindly; fix on fixtures, then spend one call to confirm.
- Check `GET /usage` at the start and end of each live session.

### Git workflow
- `main` is always runnable. One branch per phase, small commits, merge when "done when" is true.
- CI on every push: backend lint + tests (stub analyzer, no `model` or `live` markers), frontend typecheck + lint + tests, OpenAPI and type drift check, migration test on blank Postgres.
- Tag `v0.x` at each milestone.

### Definition of done (every phase)
1. Done-when criteria met.
2. Tests written and passing in CI.
3. No live SerpApi or Groq calls and no real-model loading in default tests.
4. Module README updated (inputs, outputs, failure behavior).
5. API or schema changes reflected in docs, `openapi.json`, generated types, golden fixture.
6. No secrets in the repo.

---

## 2. Milestones

| Milestone | Phases | Outcome |
|---|---|---|
| **M1: Clickable demo** | 0–1 | Full UI flow on golden data |
| **M2: Real data pipeline** | 2–6 | Real brand → real sentiment, aspects and signals on the dashboard |
| **M3: Intelligence** | 7–8 | Investigate a signal → cited evidence, competitor scope, recommendations |
| **M4: Demo-ready** | 9–10 | Hardened, polished, pre-warmed, rehearsed, with fallbacks |

Dependency notes:
- Phase 1 (frontend on golden) runs **in parallel** with Phases 2–3 once Phase 0 is done.
- Phase 4 (local NLP) needs only text and labels, not live data. It can start right after Phase 0, using recorded fixtures from Phase 2 when available.
- Phase 6 is the integration gate. Do not start Phase 7 until a real brand works end to end through the dashboard.

---

## 3. SerpApi credit plan (250 per month)

| Use | Calls | When |
|---|---|---|
| Fixture recording: one or two calls per engine, plus variants | ≤ 30 | Phase 2 |
| Demo-signal probe (see §5) | ≤ 6 | Phase 2 |
| Engine-behavior experiments (pagination, `num`, date params, multi-term Trends) | ≤ 9 | Phase 2 |
| First live end-to-end debugging (about 3 analyses) | ≤ 40 | Phase 6 |
| Live investigation tests (about 3 to 4 runs) | ≤ 30 | Phases 7–8 |
| Demo pre-warm: Samsung full flow | ≈ 20 | Phase 10 |
| Backup brand pre-warm | ≈ 20 | Phase 10 |
| Rehearsal and demo day live attempts (two flows) | ≈ 40 | Phase 10 |
| Reserve | ≈ 55 | Throughout |

Notes:
- The allowance resets monthly. If development spans two billing months, the first month's plan covers Phases 0–6 and the second covers the rest; adjust the table to your dates. If the limit is reached, switch to another SerpApi account: set a new `SERPAPI_API_KEY` and `SERPAPI_ACCOUNT_LABEL` (the monthly counter filters on the label).
- Cached replays are free. Pre-warm early, rehearse on cache.
- If a live session overspends, drop the backup-brand pre-warm first.

---

## 4. Phases

### Phase 0: Foundations and contracts (M)

**Goal:** a runnable skeleton and the contracts everything builds against.

Tasks:
- Monorepo layout from `ARCHITECTURE.md` §4.
- Backend: FastAPI app, settings (all env vars), logging, error envelope, `/health`.
- Alembic setup; first migration (enums, `brands`, `analyses`, `analysis_brands`).
- Frontend: Next.js + TS + Tailwind + shadcn/ui, `/api` rewrite, generated API types, typed client with `NEXT_PUBLIC_USE_GOLDEN` switch.
- Pydantic API schemas per `API.md`; export `contracts/openapi.json`.
- `contracts/golden/samsung_battery.json`: full analysis plus investigation report, consistent with schemas.
- `AGENTS.md`, `docs/SCORING.md`, `docs/DESIGN_SYSTEM.md`.
- CI pipeline (stub analyzer only).
- Accounts and keys: Supabase project, SerpApi, Groq.

Done when:
- `/health` returns ok with the database reachable.
- Frontend renders from the golden fixture through the typed client.
- CI green, including migration test and type-drift check.
- Golden fixture validates against the Pydantic schemas.

---

### Phase 1: Frontend on golden data (L)

**Goal:** the full user journey looks like a real product, backed by the fixture.

Tasks:
- Design tokens: white background, blue primary, light-blue secondary surfaces, navy text, light gray-blue borders; green/yellow/red only for semantic status. No dark mode.
- App shell, navigation, landing page, analyze form with live-run confirmation dialog (estimate, remaining searches, access code field), progress page (simulated states).
- Dashboard: Brand Health, sentiment summary, aspect table with click-through drawer showing the analyzed clause, topics, trend chart.
- Emerging Signal card as the focal point.
- Investigation page: steps, summary, findings with citations, confidence breakdown, scope badge, competitor table, recommendations, "generated by fallback" notice.
- Evidence explorer, competitors page, usage indicator (small, unobtrusive).
- States: skeletons, empty, error, low-data, partial-warning banner, quota-low.
- Responsive layouts.

Done when:
- Landing → analyze → dashboard → investigate → report → evidence → source URL works on golden data.
- Visual check against `DESIGN_SYSTEM.md` on desktop and mobile widths.
- Component tests for `EmergingSignalCard`, `EvidenceList`, `ConfidenceBreakdown`.

---

### Phase 2: SerpApi layer and budget machinery (L)

**Goal:** reliable, budgeted, cached collection; verified against a handful of real responses.

Tasks:
- Migrations: `serp_cache` (with `pinned`), `serp_usage` (with `account_label`; `investigation_id` as plain column, FK added in Phase 7).
- `client.py` (timeout, retries, error mapping), `cache.py` (key = hash of engine + params with absolute dates; TTL 30 days; shorter TTL for empty results), `budget.py`, `usage.py` (monthly counter, reserve guard, `ALLOW_LIVE_SERPAPI` switch), `estimator.py`.
- `query_planner.py` implementing the lean plan in `ARCHITECTURE.md` §6 (≈ 11 calls), windows from `as_of_date`.
- Parsers for Google web, Google News, Google Forums, YouTube search, Google Trends. Shopping and YouTube video details only if time and credits allow.
- `scripts/record_serp_fixtures.py`: record, sanitize (strip API key), commit under `tests/fixtures/serpapi/`.
- `scripts/probe_demo_signal.py`: cheap check that the demo scenario shows a spike (see §5).

Verify against real responses (spend credits here deliberately):
- Results per call, pagination cost, whether a `num` or page-size parameter works.
- Which engines accept date ranges and how.
- Date field format per engine (YouTube and forums likely relative or missing).
- Whether Trends accepts several terms in one call.
- Whether YouTube video details expose comments.
- Whether SerpApi bills repeated identical searches; confirm in its documentation before relying on it.
- Write findings to `docs/SERPAPI_FINDINGS.md`.

Done when:
- Every parser returns normalized `RawItem` objects from recorded fixtures.
- Cache hit avoids a call (tested). Budget exhaustion stops collection cleanly (tested). Reserve guard refuses live calls below the reserve (tested). Live switch off blocks all network calls (tested).
- Estimator output matches the planner on fixtures.
- Findings note written.
- Credits used ≤ 45.

---

### Phase 3: Processing and persistence (M)

**Goal:** clean, deduplicated, dated content in the database.

Tasks:
- Migration: `content_items`.
- `cleaner.py`, `normalizer.py` (domain, canonical URL, hashes), `dates.py` (relative-date parsing, `date_confidence`, window assignment), `dedupe.py` (exact hashes plus near-duplicate `dup_group` via normalized title and token overlap; no embeddings).
- Repositories for `content_items`.

Done when:
- Recorded fixtures flow into deduplicated `content_items` in a test database.
- Table-driven tests cover: relative dates, missing dates, duplicate URLs, syndicated titles, empty snippets.

---

### Phase 4: Local NLP (L)

**Goal:** per-item sentiment, aspect sentiment, relevance, keywords and topics from a local BERT-family model plus rules, with measured accuracy. No network, no LLM.

Tasks:
- Migration: `content_analysis`, `item_aspects`.
- `model_loader.py`: lazy singleton, CPU-only torch, configurable `SENTIMENT_MODEL` and `HF_HOME`; startup warm-up option.
- `sentiment.py`: `SentimentAnalyzer` protocol, HF implementation (batched), margin rule mapping low-confidence predictions to neutral, deterministic stub for tests.
- `relevance.py`: brand, product and alias match rules.
- `clauses.py`: sentence split, then contrast-word split.
- `taxonomy.py`: aspect lexicons for a consumer-electronics preset (battery, camera, performance, pricing, design, software, customer support, display, charging) plus a generic fallback preset. Category chosen by a form dropdown, no LLM.
- `aspects.py`, `keywords.py`, `topics.py`.
- Label 40–60 snippets by hand (overall sentiment plus aspect-level where present), mixing real snippets from Phase 2 fixtures. `scripts/run_eval.py`.
- Evaluate the model shortlist (see `ARCHITECTURE.md` §5.1); check size, license and availability on Hugging Face at this point. Choose one.
- Analyzer reuse by `(content_hash, analyzer_version)`.
- Measure memory and cold start on the local machine (no Docker, no hosting).

Done when:
- Eval meets thresholds (suggested: overall sentiment accuracy ≥ 75% and macro-F1 ≥ 0.70 on the labeled set; aspect detection recall reported separately; tune neutral margin and lexicons until acceptable).
- The "camera amazing but battery terrible" case yields camera positive, battery negative (unit test with the stub and one `model` test with the real model).
- Re-running on analyzed items performs zero inference.
- Throughput and memory numbers recorded in `docs/`.

Watch-outs: keep every analyzer behind the interface; do not let unit tests import torch.

---

### Phase 5: Signals, scoring and brand health (M)

**Goal:** transparent, tunable emerging-signal detection and health scoring on lean samples.

Tasks:
- Migration: `trend_points`, `brand_snapshots`, `signals`.
- `signals/metrics.py`: per-window shares over growth sources (news, web).
- `signals/detector.py`: smoothed growth, lean guards, thresholds.
- `signals/scoring.py`: signal score, impact, sample-size-aware signal confidence.
- `scoring/health.py`.
- Trends corroboration flag.
- All weights and thresholds in `scoring_config.py`.

Done when:
- A fixture dataset with a planted battery spike yields the expected HIGH-impact signal.
- Boundary tests: below guards, no baseline, flat trend, equal windows, only non-growth sources.
- Weights change via config only (tested).

---

### Phase 6: Analysis pipeline and first real end-to-end (L)

**Goal:** enter a real brand and see a real dashboard. Integration gate.

Tasks:
- `pipeline/analysis_pipeline.py`: stages, progress, per-stage transactions, partial-failure policy, warnings.
- `pipeline/jobs.py`: `BackgroundTasks` runner, concurrency limit, stale-job reaper.
- Migration: `llm_calls` (`investigation_id` plain column until Phase 7). Minimal `llm/` provider + limiter for competitor suggestion; Phase 7 completes it.
- `DEMO_MODE`: alias IDs (`demo`, `demo-signal-battery`, `demo-investigation`) served from the golden fixture; `scripts/seed_demo.py`.
- API: `POST /analyses`, `POST /analyses/estimate`, `GET /analyses`, `GET /analyses/{id}`, `GET /analyses/{id}/dashboard`, `GET /analyses/{id}/mentions`, `GET /signals/{id}`, `GET /usage`, `GET /health`.
- Access-code check for live runs; daily cap; per-IP rate limit; quota errors.
- Competitors: maximum 2; current-window snapshots; if none given, suggest up to 2 via Groq (logged in `llm_calls`).
- Frontend: leave golden mode; confirmation dialog uses real estimate; progress polls real status.
- Run everything locally (decided: no hosting). Document local run steps in the README.
- Live debugging budget: ≤ 40 calls. Debug on cache and fixtures first.

Done when:
- A real run (Samsung Galaxy S25 Ultra, pinned date) produces a real dashboard.
- The e2e test (fake SerpApi + stub analyzer + test DB) matches the golden dashboard shape.
- A mid-pipeline failure produces `partial` with a warning.
- Repeating the same run uses zero new SerpApi calls (cache proof).
- With `DEMO_MODE=true`, alias IDs return the golden dashboard.

---

### Phase 7: Groq and investigation (L)

**Goal:** click Investigate, get an evidence-backed, cited explanation with computed confidence.

Tasks:
- Migration: `investigations`, `evidence`; add FKs from `serp_usage.investigation_id` and `llm_calls.investigation_id`.
- `llm/`: finish the module started in Phase 6 — provider protocol, `provider_groq.py`, `structured.py`, `limiter.py` (concurrency 1, `retry-after`, per-investigation call cap), `fallback.py`, prompts as versioned files.
- Choose `GROQ_MODEL` by running the golden evidence set through free-tier candidates; check Groq's current model list and limits at that time.
- `query_gen.py`, `evidence_collector.py` (≤ 8 SerpApi calls), `evidence_scorer.py`, `confidence.py`, `synthesizer.py` with citation validation, `scope.py` hook.
- `pipeline/investigation_pipeline.py` with step tracking.
- API: `POST /signals/{id}/investigate` (idempotent), `GET /investigations/{id}`, `GET /investigations/{id}/evidence`.
- Frontend wired to real endpoints.
- Live budget: ≤ 30 calls across Phases 7–8.

Done when:
- Investigating the planted fixture signal returns a report whose every citation resolves.
- Citation guard strips a hallucinated evidence ID (test).
- No-evidence case returns inconclusive, Low confidence.
- Groq quota exhaustion triggers the fallback report, marked as such (test).
- Double-click creates one investigation.
- A full investigation uses ≤ 8 Groq calls (asserted in test with stub).

Watch-outs: "associated with", not "caused by". Confidence comes from the formula only.

---

### Phase 8: Competitors and recommendations (M)

**Goal:** answer "our problem or the market's?" and say what to do.

Tasks:
- Migration: `recommendations`.
- `competitors/comparison.py`: targeted aspect check per competitor (reuses cached snapshot data first; spends at most the planned 2 calls).
- `competitors/scope.py`: ratio-based verdict, "currently" wording.
- `recommendations/generator.py`: actions from signal + evidence + competitor context, each with valid evidence IDs; priority from impact and confidence.
- Frontend: competitor table in report; recommendations with linked evidence.

Done when:
- Planted data yields `brand_specific`; equal competitor data yields `industry_wide`; missing data yields `unknown`.
- Every recommendation has non-empty valid `evidence_ids`.
- The golden flow reproduces with real components and fake external services.

---

### Phase 9: Hardening and testing (M)

**Goal:** the product fails gracefully, especially under free-tier limits.

Tasks:
- Implement and test the full failure matrix in `ARCHITECTURE.md` §10.
- Quota paths: reserve reached, live switch off, cache-only mode with clear UI messages.
- Model-unavailable path (`/health` shows NLP status; analysis start refuses cleanly).
- Warning surfacing in the UI.
- Structured logging with analysis and investigation IDs.
- Security pass: no keys in logs or responses, RLS enabled on all tables, input length limits, access code not logged.

Done when: every row of the failure matrix has a passing test and the UI shows a sensible state for each.

---

### Phase 10: Demo bundle, pre-warm, polish and rehearsal (M)

**Goal:** a demo that cannot embarrass you.

Tasks:
- Pre-warm: run the Samsung analysis and investigation once live (≈ 20 calls), then verify a repeat costs zero.
- `export_demo_bundle.py`: dump the real analysis, investigation and the SerpApi cache entries to `contracts/demo/samsung_s25_ultra.json`. `DEMO_MODE` can serve it with no database, no model and no network.
- Mark all cache entries used by the demo as `pinned` (never expire or purge).
- Optional backup brand pre-warm.
- Polish: charts, loading and error states, evidence display, investigation experience. Minimal, purposeful animation.
- Demo script; rehearse twice (live-cached path and bundle fallback).

Done when: the PRD success flow runs uninterrupted: enter brand → collect → sentiment/topics/aspects → emerging signal → Investigate → independent evidence → competitor comparison → explanation → recommendation. Works on cache and on the bundle fallback.

---

## 5. Demo scenario

**Brand and product:** Samsung, Galaxy S25 Ultra. Competitors: Apple and OnePlus (from the PRD).

**Why this scenario:** public reports in late July 2026 describe battery drain, overheating and slower charging on Galaxy S24 Ultra and S25 Ultra after the July 2026 update (One UI 8.5), reported on Samsung's community forums and Reddit, with Samsung not having responded at the time. A WhatsApp encrypted-backup theory circulated as a likely trigger. An earlier similar wave followed the April 2026 update (reports blamed Knox Matrix). Reference articles:
- https://9to5google.com/2026/07/30/samsung-galaxy-battery-drain-july-update-issues/
- https://www.businesstoday.in/technology/news/story/samsung-galaxy-s24-ultra-s25-ultra-battery-drain-complaints-after-july-security-update-546302-2026-07-30
- https://www.phonearena.com/news/galaxy-s25-ultra-s24-ultra-another-frustrating-issue_id182183

**Pinned date:** set `as_of_date` to about 2026-08-10 with `period_days = 30`. Current window ≈ 11 July–10 August, baseline ≈ 11 June–10 July. This captures the spike. Running with today's date (October) would likely show a decayed signal.

**Caveats:**
- The numbers will not equal the PRD's example (4.2×). Whatever the data shows is what the demo shows.
- The April wave may leak into the baseline and shrink the growth ratio. The probe will show this.
- YouTube and forum results cannot be date-filtered, so they reflect today's content. They only corroborate, and the UI shows their dates.
- Pixel phones had their own battery drain problem in the same period according to press coverage. If you pick Google as a competitor, expect the verdict to move toward industry-wide, which can be a useful second demo.

**Probe (Phase 2, ≤ 6 calls):** Google News for "Samsung Galaxy S25 Ultra battery" in each window, plus one web search per window, plus one forums search. If the current window shows no more battery-negative coverage than the baseline, switch to the April 2026 window or another scenario before building on this one.

**Script:**
1. Enter brand, product, competitors. Confirm estimate (cached → zero new searches).
2. Progress screen while data processes.
3. Dashboard: Brand Health, sentiment, aspects. Click battery to show real clauses and sources.
4. Emerging Signal card: growth, impact, confidence, sample size, sources. Click **Investigate**.
5. Investigation: steps run, summary appears with citations. Open the evidence explorer, click through to an original URL.
6. Competitor comparison and scope verdict.
7. Recommendations tied to evidence.

**Fallback ladder:** live → cached (pre-warmed) → demo bundle. Switch silently if a service stalls.

**Rehearsal checklist:** keys valid, quota checked with `/usage`, cache pre-warmed, backend running locally and warm (model loaded), signal verified, backup recording of a successful run.

---

## 6. Environment and secrets

Backend `.env`:

| Variable | Purpose / default |
|---|---|
| `DATABASE_URL` | Pooled app connection to Supabase Postgres |
| `DATABASE_URL_DIRECT` | Direct or session connection for Alembic |
| `SERPAPI_API_KEY` | SerpApi |
| `SERPAPI_ACCOUNT_LABEL` | Label for the current SerpApi account. Monthly counter filters on it. Change it when you switch accounts |
| `ALLOW_LIVE_SERPAPI` | `false` by default |
| `SERP_MONTHLY_LIMIT` | `250` |
| `SERP_MONTHLY_RESERVE` | `20` |
| `SERP_BUDGET_PER_ANALYSIS` | `12` |
| `SERP_BUDGET_PER_INVESTIGATION` | `8` |
| `SERP_CACHE_TTL_HOURS` | `720` (30 days) |
| `LIVE_ACCESS_CODE` | Optional. Header value for live runs; empty = no check (local use) |
| `MAX_ANALYSES_PER_DAY` | `3` (global) |
| `MAX_CONCURRENT_ANALYSES` | `1` |
| `SENTIMENT_MODEL` | Hugging Face model id, chosen in Phase 4 |
| `HF_HOME` | Model cache directory |
| `GROQ_API_KEY` | Groq |
| `GROQ_MODEL` | Chosen in Phase 7 |
| `LLM_MAX_CONCURRENCY` | `1` |
| `LLM_MAX_CALLS_PER_INVESTIGATION` | `8` |
| `DEMO_MODE` | `true` serves golden or demo bundle for alias IDs |
| `CORS_ORIGINS`, `LOG_LEVEL` | |

Frontend `.env`:

| Variable | Purpose |
|---|---|
| `API_PROXY_TARGET` | Backend URL for the Next.js rewrite |
| `NEXT_PUBLIC_USE_GOLDEN` | `1` reads the fixture instead of the API |

Keep `.env` out of git; commit only `.env.example`. The access code is stored in the browser session only, never in frontend env.

---

## 7. Risk register

| Risk | Phase | Mitigation |
|---|---|---|
| Free-tier SerpApi runs out | all | Budget plan, `ALLOW_LIVE_SERPAPI` off by default, estimate-before-run, cache, reserve, access code |
| Local machine too small for torch + model | 4 | Check about 2 GB free RAM in Phase 4; demo bundle fallback needs no model |
| Small samples produce weak or no signals | 5 | Lean guards, sample-size-aware confidence, probe before building on the scenario |
| SerpApi date quality poor | 2–3 | Verify early; honest `date_confidence`; growth only from news and web |
| Lexicon aspect detection misses phrasing | 4 | Eval recall; extend lexicons from real snippets |
| BERT model weak on very short snippets | 4 | Eval; margin to neutral; compare shortlist |
| Groq free-tier throttling or model weakness | 7 | ≤ 8 calls, small prompts, validation, citation guard, deterministic fallback |
| Demo scenario shows no signal | 2, 6 | Probe in Phase 2; backup scenario (April 2026 window) |
| Backend restart kills jobs | 6 | Stale-job reaper; warm-up before demo |
| Agent creates sprawling code | all | One module per prompt, AGENTS.md, CI |
| Scope creep into BERTopic, FAISS, Redis, auth | all | Backlog list below |

---

## 8. Backlog (after MVP)

- Aspect-based BERT model (ABSA) to replace lexicon plus clause sentiment; ONNX or quantized inference for lower memory.
- BERTopic and sentence embeddings for topics and near-duplicate detection; FAISS for semantic evidence retrieval.
- Redis for caching and rate limiting; a real job queue.
- Supabase Auth, workspaces, shareable reports, PDF export.
- Scheduled monitoring and alerts.
- Paid SerpApi plan to remove sample-size and budget limits; baseline windows for competitors.
- More engines: Instagram profile, YouTube channel analysis, Search Index, Shopping-based pricing signals.
- `topic_surge` and positive-signal detection.

---

## 9. Decisions (resolved)

1. **Hosting:** none. Local run only (hackathon MVP).
2. **Pinned date:** `as_of_date` 2026-08-10 confirmed.
3. **Billing:** monthly allowance; if the limit is reached, switch to another SerpApi account (new key + new `SERPAPI_ACCOUNT_LABEL`).
4. **Language:** English only.