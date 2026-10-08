# BrandPulse AI: MVP Architecture (v2)

Stack: Next.js + TypeScript + Tailwind + shadcn/ui · FastAPI · Supabase PostgreSQL · SerpApi (only external data provider, **free plan: 250 searches/month**) · Groq (only LLM provider, **free tier**) · local BERT-family model for NLP. Runs on the developer's machine only (hackathon MVP, no hosting).

No Redis, microservices, Kubernetes, queues or extra infrastructure.

Companion documents: `DATABASE.md`, `API.md`, `DEVELOPMENT_PLAN.md`, and (written in Phase 0) `docs/SCORING.md`, `docs/DESIGN_SYSTEM.md`, `AGENTS.md`.

**What changed from v1:** NLP is now local (BERT-based sentiment + rule-based aspects) instead of LLM batches; Groq is used only for investigation reasoning; the whole design is budget-first because of the 250-search SerpApi limit.

---

## 1. Constraints that shape the design

| Constraint | Consequence |
|---|---|
| SerpApi free plan: 250 searches per month, shared by development, testing and demo | Fixture-first development. No live calls in tests. Persistent cache. Pinned `as_of_date` so cache keys stay stable. Monthly counter with reserve. Cost estimate before every live run. Pre-warmed demo. |
| Groq free tier: tight request and token limits (verify current numbers at setup) | LLM used only where reasoning is needed (≤ 8 calls per investigation). Concurrency 1. Rate-limit handling. Deterministic fallback text when quota is gone. |
| Local BERT model | CPU-only torch, model loaded once at startup, weights cached in `HF_HOME`. Runs locally only (no hosting); needs about 2 GB free RAM. See §11. |
| Small samples (few items per search call) | Growth is computed only from reliably dated sources; thresholds are lean; every signal shows sample size and a sample-size-aware confidence. |

---

## 2. Key decisions

| # | Decision | Why |
|---|---|---|
| 1 | Modular monolith, one monorepo: one FastAPI process, one Next.js app. | Easy to prompt, run and debug. |
| 2 | **Backend is the only DB accessor.** Browser talks to FastAPI only. | One contract. No RLS puzzle. |
| 3 | Long jobs = FastAPI `BackgroundTasks` + status columns + 2 s polling. Single worker. Stale-job reaper on startup. | No queue, no Redis. |
| 4 | Sync SQLAlchemy 2 + Alembic. Sync `httpx` with a small thread pool. | Simpler for AI agents than async. |
| 5 | **NLP = local BERT-family sentiment model + rule-based aspect detection + clause-level sentiment.** No LLM in the analysis path. BERTopic, FAISS and sentence embeddings are deferred. | Your decision. Also saves Groq quota and makes results deterministic and testable. |
| 6 | **Budget-first SerpApi design** (see §6). | 250 searches/month total. |
| 7 | Trend math uses **mention share**, not raw counts. Growth uses only sources with reliable dates in both windows (news, web). YouTube and forums corroborate but do not drive growth. | Raw counts mislead on capped samples. Relative dates from YouTube and forums are unreliable. |
| 8 | Confidence is a **deterministic formula**. LLM never invents the number. | Defensible, testable. |
| 9 | LLM may cite evidence IDs only. Backend validates IDs and drops uncited claims. | Kills hallucinated sources. |
| 10 | Golden fixture (synthetic) now; real **demo bundle** exported from a live run later. | Frontend development, contract tests, demo fallback. |
| 11 | Groq: one model via `GROQ_MODEL`. Current MVP uses it for synthesis/reasoning; investigation query templates and cached-evidence scoring remain deterministic and cache-safe. | Free tier. Minimal calls. |
| 12 | NLP results reused across analyses by `(content_hash, analyzer_version)`. | Saves CPU time on repeated content. |
| 13 | Cache keys use absolute window dates from a pinned `as_of_date`. | Relative "last 30 days" windows would change daily and miss the cache. |

---

## 3. System shape

```text
Browser (Next.js)
   │  REST JSON /api/v1   (Next.js rewrite → FastAPI)
   ▼
api/  thin routers, validation, DTO mapping, access-code and quota checks
   ▼
pipeline/  orchestrators (analysis, investigation). ONLY layer that wires modules + repos
   │
   ├─ services/serpapi ────► SerpApi  (+ serp_cache, serp_usage, budget, quota guard)
   ├─ services/processing     clean / normalize / dedupe / dates
   ├─ services/nlp ────────► local HF model (CPU) + lexicons   (no network)
   ├─ services/signals        pure math
   ├─ services/scoring        pure math (health)
   ├─ services/investigation ► serpapi + llm
   ├─ services/competitors
   ├─ services/recommendations ► llm
   ├─ services/llm ────────► Groq (free tier, rate-limited)
   └─ db/repositories ─────► Supabase Postgres
```

Layering rules:
- I/O at the edges: serpapi client, llm client, model loader, repositories.
- Logic in the middle: pure functions, Pydantic in, Pydantic out.
- Services never import each other, `api/`, or DB models.
- Only `pipeline/` calls repositories.
- NLP depends on a `SentimentAnalyzer` interface, so tests use a deterministic stub and never load the model.

---

## 4. Folder structure

```text
brandpulse/
├── AGENTS.md
├── docs/  (PRD.md, ARCHITECTURE.md, DATABASE.md, API.md, DEVELOPMENT_PLAN.md, SCORING.md, DESIGN_SYSTEM.md, SERPAPI_FINDINGS.md)
├── contracts/
│   ├── openapi.json
│   ├── golden/samsung_battery.json        # synthetic, for UI + contract tests
│   └── demo/samsung_s25_ultra.json        # real exported run (Phase 10)
├── .github/workflows/ci.yml
│
├── backend/
│   ├── pyproject.toml  .env.example
│   ├── alembic/versions/
│   ├── scripts/           # record_serp_fixtures, probe_demo_signal, warm_demo_cache,
│   │              # export_openapi, export_demo_bundle, seed_demo, run_eval
│   ├── app/
│   │   ├── main.py
│   │   ├── config/                # settings.py scoring_config.py taxonomy.py (aspect lexicons per category)
│   │   ├── api/v1/                # analyses.py signals.py investigations.py usage.py health.py errors.py deps.py
│   │   ├── schemas/               # api.py domain.py llm_io.py
│   │   ├── pipeline/              # analysis_pipeline.py investigation_pipeline.py jobs.py
│   │   ├── services/
│   │   │   ├── serpapi/           # client.py cache.py budget.py usage.py query_planner.py estimator.py parsers/<engine>.py
│   │   │   ├── processing/        # cleaner.py normalizer.py dedupe.py dates.py
│   │   │   ├── nlp/               # model_loader.py sentiment.py (protocol + HF impl + stub) clauses.py aspects.py relevance.py keywords.py topics.py
│   │   │   ├── llm/               # base.py provider_groq.py service.py structured.py limiter.py fallback.py prompts/*.md
│   │   │   ├── signals/           # metrics.py detector.py scoring.py
│   │   │   ├── scoring/           # health.py
│   │   │   ├── investigation/     # query_gen.py evidence_collector.py evidence_scorer.py confidence.py synthesizer.py
│   │   │   ├── competitors/       # snapshot.py comparison.py scope.py
│   │   │   └── recommendations/   # generator.py
│   │   ├── db/                    # session.py models/ repositories/
│   │   └── utils/
│   └── tests/                     # unit/ parsers/ integration/ e2e/ evals/ fixtures/{serpapi,llm}/
│
└── frontend/
    ├── app/  (landing, analyze, analyze/[id], dashboard/[id], signals, competitors, evidence)
    ├── components/ (ui, layout, dashboard, signals, evidence, competitors, recommendations, common)
    └── lib/ (api client + hooks + generated types, format.ts)
```

### AGENTS.md rules
1. One phase and one module per prompt.
2. Read that module's README and the relevant fixture first.
3. **Never call live SerpApi or Groq in tests or while developing**, unless the prompt explicitly says so and `ALLOW_LIVE_SERPAPI=true` is set. Every live call spends a scarce monthly credit.
4. Never load the real NLP model in unit tests; use the stub analyzer. Model tests carry the `model` marker.
5. Pure logic stays out of routers and repositories.
6. All scores come from the backend. Frontend only formats.
7. API change → regenerate `openapi.json` and TS types; update golden fixture.
8. Colors from tokens only. Red, yellow, green only for semantic status.
9. No new dependency without asking.

---

## 5. Module responsibilities

| Module | Owns | In → Out |
|---|---|---|
| `serpapi/client` | HTTP, timeout, retries, error mapping | `QuerySpec` → raw response |
| `serpapi/cache` | Persistent cache by hash of engine + params (absolute dates) | spec → hit or miss |
| `serpapi/budget` + `usage` | Per-analysis and per-investigation caps; monthly counter; reserve guard; live-call kill switch | spec → allow or deny |
| `serpapi/estimator` | Counts cached vs new calls a plan would need, without calling | plan → estimate |
| `serpapi/query_planner` | (engine, query, window) tuples under budget | brand, product, as_of → plan |
| `serpapi/parsers/*` | One parser per engine | raw → `RawItem[]` |
| `processing/` | Clean, normalize, parse relative dates, dedupe (hash + near-duplicate group) | `RawItem[]` → `ContentItem[]` |
| `nlp/relevance` | Rule-based brand match: name, product, aliases in title or snippet | item → `is_about_brand`, matched terms |
| `nlp/clauses` | Sentence split, then split on contrast words (but, however, although, while, yet) | text → clauses |
| `nlp/aspects` | Lexicon-based aspect detection per category preset; maps each aspect to its clause | clauses → (aspect, clause) pairs |
| `nlp/sentiment` | `SentimentAnalyzer` protocol; HF model implementation (batched, CPU); low-margin predictions become `neutral`; deterministic stub for tests | texts → label + score |
| `nlp/keywords`, `topics` | Lightweight frequency/TF-IDF keywords; topics = aspects plus top keywords | items → keywords, topics |
| `llm/` | Groq provider, schema-constrained JSON, validate + retry once, limiter, `fallback.py` templates | prompt + schema → typed object |
| `signals/` | Window metrics, growth, detection, signal score, impact, signal confidence | analyses → `SignalCandidate[]` |
| `scoring/` | Brand Health | snapshot → scores |
| `investigation/` | Hypotheses → queries; fetch evidence; stance tagging; confidence formula; cited synthesis | signal → `InvestigationReport` |
| `competitors/` | Snapshots; targeted aspect comparison; scope verdict | snapshots → comparison + scope |
| `recommendations/` | Actions linked to evidence IDs; priority from impact and confidence | report → `Recommendation[]` |
| `pipeline/` | Stage order, progress, partial-failure policy, warnings | request → persisted results |

### 5.1 Local NLP pipeline

```text
ContentItem (title + snippet)
   → relevance rule (drop if not about brand)
   → overall sentiment: model on full text → positive / neutral / negative + score
   → clause split → aspect lexicon match → clause per aspect
   → aspect sentiment: model on each aspect clause
   → keywords + topics
   → content_analysis + item_aspects rows (clause stored for evidence display)
```

- Handles the PRD example "The camera is amazing but battery life is terrible": split on "but", camera clause → positive, battery clause → negative.
- Model shortlist (verify size, license and availability on Hugging Face in Phase 4, then pick by eval): a 3-class RoBERTa sentiment model (for example `cardiffnlp/twitter-roberta-base-sentiment-latest`), a binary DistilBERT SST-2 model with a confidence margin for neutral, or a small multilingual 3-class DistilBERT. Start with the 3-class RoBERTa model.
- Aspect-specific BERT models (ABSA) are a possible later upgrade; lexicon plus clause sentiment is the MVP.
- Inference is CPU batched (16–32 texts per batch). Target: a few hundred short texts in well under a minute. Verify in Phase 4.
- `analyzer_version` = model name + lexicon version + rule version. Changing any of them invalidates reuse.

### 5.2 Groq usage rules (free tier)

- Used only where implemented: synthesis/reasoning and optional competitor suggestion. Investigation query templates and cached-evidence scoring are deterministic in the current MVP.
- Budget: ≤ 6 calls per investigation normally, hard cap `LLM_MAX_CALLS_PER_INVESTIGATION` = 8 including retries.
- Keep input small: snippets truncated (about 200 characters), at most about 30 evidence items per investigation, batches of 15–20 for stance tagging.
- Concurrency 1. Honor `retry-after` on 429. Log every call in `llm_calls`.
- Always validate output with Pydantic and retry once. Short single-purpose prompts.
- If Groq is unavailable or quota is exhausted: `fallback.py` produces a template-based summary, rule-based stance (from aspect sentiment of the evidence clause) and templated recommendations. The report is marked `generated_by: "fallback"` so the UI can say so.
- Pick `GROQ_MODEL` in Phase 7 by running the golden evidence set through candidates available on the free tier. Check Groq's current model list and limits at that time.

### 5.3 Pipeline stages

Analysis: `planning → collecting → processing → analyzing → detecting → snapshotting → done`. Status: `queued | running | completed | partial | failed`. `partial` = usable data plus `warnings[]`.

Windows (from `as_of_date`, default today; pinned for demo):
- Current = `period_days` ending at `as_of_date`.
- Baseline = preceding equal span.
- Absolute dates are passed to engines that support date ranges.

Competitors: current-window snapshot only (no baseline), keeping their cost at 2 calls each (1 news + 1 web). **Maximum 2 competitors.** If none given, one Groq call suggests 2. At investigation time: targeted aspect check per competitor.

### 5.4 Investigation (fixed bounded pipeline)

1. Groq proposes hypotheses and queries (validated, capped).
2. Investigation MVP reuses existing cached content; it does not spend new SerpApi credits.
3. Deterministic evidence scoring assigns stance/relevance; Groq synthesis is optional and evidence IDs are validated.
4. `confidence.py` computes the score.
5. `scope.py` computes the verdict.
6. Groq writes summary and findings citing evidence IDs; backend validates.
7. Recommendations generated and validated.

Use "associated with", not "caused by".

---

## 6. SerpApi budget design (250 searches/month)

### Lean default plan: one analysis, target + 2 competitors (≈ 11 calls; 2 is the maximum, so 11–12 is the ceiling)

| Calls | Engine | Detail |
|---|---|---|
| 1 | Google Trends | All three brands in one multi-term timeseries call (verify support in Phase 2) |
| 2 | Google News | Target: current and baseline |
| 2 | Google web search | Target "brand product review problems": current and baseline |
| 1 | YouTube search | Target, current only |
| 1 | Google Forums | Target, current only |
| 2 | Google News | Competitors, current only (1 each) |
| 2 | Google web search | Competitors, current only (1 each) |

Default cap `SERP_BUDGET_PER_ANALYSIS` = 12.

### Investigation plan (≤ 8 calls)
News 1, forums 1, YouTube 1, web 2 (hypothesis queries), Trends 1 (aspect keyword across brands), competitor aspect web checks 2.

Default cap `SERP_BUDGET_PER_INVESTIGATION` = 8.

### Full flow ≈ 19–20 calls → about 12 complete runs per month if development used none. Planned allocation of the 250:

| Use | Calls |
|---|---|
| Phase 2: fixture recording, engine verification, demo probe | 45 |
| Phase 6: first live end-to-end debugging | 40 |
| Phases 7–8: live investigation tests | 30 |
| Demo pre-warm: Samsung (one full flow) | 20 |
| Backup demo brand pre-warm | 20 |
| Rehearsal and demo day live attempts (two flows) | 40 |
| Reserve | 55 |

### Safeguards
- `ALLOW_LIVE_SERPAPI=false` by default. Dev and CI run on cache and fixtures only.
- `serp_usage` table logs every call (credits spent vs cache hit). Monthly counter derives from it, filtered by `SERPAPI_ACCOUNT_LABEL`, so switching to a fresh SerpApi account (new key + new label) starts a clean count.
- `SERP_MONTHLY_LIMIT` = 250, `SERP_MONTHLY_RESERVE` = 20. Live calls are refused when the remainder would fall below the reserve. Daily analysis cap is global: `MAX_ANALYSES_PER_DAY` = 3.
- `POST /analyses/estimate` returns `estimated_new_calls` and `cached_calls` before running. UI confirms: "This run will use about N of M remaining searches."
- `LIVE_ACCESS_CODE` (optional; empty = disabled): when set, live (non-cached) runs need the access code header. Not needed for local-only use.
- Cache TTL 30 days in free-tier mode. Cache can be exported and committed (demo bundle) so the demo survives a database reset. Demo entries are marked `pinned` and never expire or get purged.
- Check in Phase 2 how many results one call returns and what pagination costs. If a call returns only about 10 results, samples are small; this is why thresholds are lean (§8).

---

## 7. Interfaces

- **API:** see `API.md` (adds `estimateAnalysis` and `getUsage` to the earlier set; `X-Access-Code` header for live runs).
- **Database:** see `DATABASE.md` (adds `serp_usage`, `analyses.as_of_date`, `item_aspects.clause`; content analysis keyed by `analyzer_version`).

---

## 8. Scoring specs

Detail goes in `docs/SCORING.md`; weights in `scoring_config.py`. Starting values, to be tuned on real data.

- **Signal unit:** (brand, aspect) negative-mention share per window.
- **Growth sources:** `news` and `web` items (reliable dates, both windows). `share_w = n_w / N_w` over growth sources.
- **Growth:** `(share_cur + ε) / (share_base + ε)`, ε = 0.02.
- **Guards (lean, configurable):** `n_cur ≥ 3` aspect-negative growth-source items and `N_cur ≥ 12` growth-source items, and `N_cur_all ≥ 15`. Below guards → `low_data`, no signal.
- **Components (each 0–1):**
  - `G = clamp(log2(growth) / log2(5))`
  - `F = clamp(share_cur_all / 0.25)`, over all current-window items
  - `C = distinct source types with aspect-negative mentions / 4`
  - `S = mean negative-class probability of aspect-negative clauses`
- **Signal score** = `0.35G + 0.20F + 0.25C + 0.20S`. Flag at ≥ 0.60. Impact: HIGH ≥ 0.75, MEDIUM 0.60–0.75.
- **Signal confidence** = sample-size factor (`min(1, N_cur_all / 40)`), source diversity, date confidence, search-interest corroboration. Small samples cap it visibly.
- **Investigation confidence** = `100 × (0.30·independence + 0.25·agreement + 0.20·signal_strength + 0.15·recency + 0.10·consistency)`. Independence counts distinct supporting domains with syndicated duplicates collapsed. Cap 95. Fewer than 2 independent sources → forced Low.
- **Scope verdict:** brand aspect-negative share ÷ median competitor share. ≥ 1.5 brand-specific; ≤ 1.2 industry-wide; between inconclusive; no usable competitor data unknown. Competitor shares come from current-window snapshots, so verdict wording says "currently".
- **Brand Health** = `0.35·Sentiment + 0.20·Engagement + 0.25·Risk + 0.20·Trend`. Risk inverted (100 = no risk). Engagement is a weak proxy; UI marks it lower confidence.

---

## 9. Development phases

Summary only. Full detail, tasks and done-criteria are in `DEVELOPMENT_PLAN.md`.

| # | Build |
|---|---|
| 0 | Skeleton, contracts, golden fixture, CI, accounts |
| 1 | Frontend on golden data |
| 2 | SerpApi layer, cache, budget and quota guard, fixtures, demo-signal probe |
| 3 | Processing and persistence |
| 4 | Local NLP (BERT sentiment, aspects, clauses) + eval |
| 5 | Signals, scoring, brand health |
| 6 | Analysis pipeline, estimate and usage endpoints, `llm_calls` migration, `DEMO_MODE` + seed, first real end-to-end (local run) |
| 7 | Groq setup + investigation |
| 8 | Competitors and recommendations |
| 9 | Hardening and failure matrix |
| 10 | Demo bundle, pre-warm, polish, rehearsal |

---

## 10. Testing strategy

| Layer | What | How |
|---|---|---|
| Unit | Dedupe, date parsing, clause splitting, aspect matching, growth, scores, confidence, scope, health | pytest, table-driven, pure functions |
| NLP eval | Sentiment and aspect accuracy | 40–60 hand-labeled snippets; `run_eval.py` reports accuracy and macro-F1 per candidate model; run manually on model or lexicon change |
| NLP model tests | Real model loads and classifies; batch throughput smoke test | `@pytest.mark.model`, excluded from default CI; run locally or nightly; HF cache directory cached in CI if enabled |
| Parser | Every engine parser | Recorded SerpApi JSON; `@pytest.mark.live` for manual smoke only |
| Budget and quota | Cache hit avoids call; budget stops collection; monthly guard refuses below reserve; live switch off blocks calls; estimator matches planner | Fake SerpApi transport |
| LLM contract | Schema validity, retry-once, 429 with `retry-after`, call cap, fallback path | Stub provider; citation-guard test strips hallucinated IDs |
| Repository / migration | SQL, `alembic upgrade head` on blank DB | Postgres service container in CI |
| API / e2e | POST → poll → dashboard → investigate → report | TestClient + fake SerpApi + stub analyzer + fake LLM + test DB; compare shape to golden |
| Contract | API ↔ frontend drift | CI regenerates `openapi.json` + TS types; fails on diff |
| Frontend | Strict TS, ESLint, Vitest + RTL for key components, 1–2 Playwright smoke tests on golden | Visual check against DESIGN_SYSTEM |

### Failure matrix (Phase 9)

| Failure | Expected behavior |
|---|---|
| SerpApi timeout / 429 / bad key | Retry with backoff, then warn. `partial` if some engines worked, `failed` if none. |
| Monthly quota at reserve | Live call refused with clear error; cached data still served |
| Live switch off and cache miss | Warning `live_data_disabled`; analysis uses cached data only or fails clearly |
| Empty results | "Not enough data" state, no fake signals |
| Duplicates / syndicated news | Collapsed before counting; independence counts domains |
| Invalid or undated items | Dropped, or kept for sentiment only with low `date_confidence` |
| Model fails to load | Backend refuses analysis start with a clear error; `/health` shows `nlp: unavailable` |
| Groq invalid JSON | Retry once, then fallback or warning |
| Groq 429 / quota exhausted | Honor `retry-after`; then deterministic fallback report marked `fallback` |
| No evidence found | "Inconclusive", confidence forced Low |
| Competitor data thin or wrong brand | Scope `unknown`, UI says so |
| DB error mid-pipeline | Job `failed` with error; reaper cleans stale jobs |
| Budget exhausted | Stop collecting, continue with what exists, warn |
| Double-click Investigate | Returns existing investigation, no extra credits |

---

## 11. Risks and open points

- **Local-only run.** Backend runs on the developer machine (torch + model need about 2 GB free RAM). No hosting in the MVP. Demo fallback: golden or demo bundle served in `DEMO_MODE`, which needs no model.
- **Small samples.** Few results per call and 12 calls per analysis mean weak statistics. The UI must show sample sizes. Lean thresholds trade false positives for detectability; tune on the demo data.
- **SerpApi date quality** varies by engine. Verify in Phase 2.
- **Snippet-level text** gives noisy sentiment. Check whether YouTube video details expose comments.
- **Lexicon recall.** Rule-based aspects miss unusual phrasing. Eval it, extend lexicons from real snippets.
- **Groq limits and model quality** on the free tier. Mitigated by small prompts, validation, citation guard and fallback.
- **Pinned-date demo.** Pinning `as_of_date` in the past makes cached results deterministic, but YouTube and forum results (no date filter) reflect today's content. Use their published dates where present; otherwise they only corroborate.
- **Credit burn.** Access code, daily cap, reserve, estimate-before-run.
- **Cut from MVP:** Instagram Profile, Search Index, YouTube Channel; Shopping optional and late.

### Decisions (resolved)
1. Hosting: none. Local run only (hackathon MVP).
2. Pinned-date demo confirmed: Samsung Galaxy S25 Ultra, `as_of_date` 2026-08-10.
3. SerpApi allowance resets monthly. If the limit is reached, switch to another account (new `SERPAPI_API_KEY` + `SERPAPI_ACCOUNT_LABEL`).
4. English only.