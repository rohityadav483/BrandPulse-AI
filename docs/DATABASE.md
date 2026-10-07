# BrandPulse AI: Database Design

Database: Supabase PostgreSQL. Access: FastAPI backend only. ORM and migrations: SQLAlchemy 2 + Alembic. Alembic models are the source of truth for the schema; this document is the design they implement.

**v2 changes:** local BERT NLP (analysis keyed by `analyzer_version`, clause stored per aspect), SerpApi free-plan budgeting (`serp_usage`, `analyses.as_of_date`), Groq used only for investigation (`llm_calls` tasks reduced).

---

## 1. Principles

1. **Backend is the only client.** The browser never queries the database. The frontend sees API DTOs, not rows.
2. **Real columns for anything filtered, joined or aggregated.** `jsonb` only for display-only blobs (score breakdowns, warnings, comparison tables).
3. **One normalized store for content.** Items collected during analysis and items fetched during investigation both live in `content_items`. Evidence is a link table, not a copy.
4. **Every insight traces to a source.** Signal → evidence → content item → original URL. No orphan claims.
5. **Aggregates are stored.** `brand_snapshots` and `signals` hold computed results so dashboard reads are cheap and stable.
6. **Everything is rebuildable.** Raw SerpApi responses are cached, so processing and analysis can be re-run without spending credits.
7. **UUID primary keys** (`gen_random_uuid()`), `timestamptz` for all timestamps, `snake_case` names, enums as Postgres enums or `text` with check constraints (pick one and stay consistent; text + check is easier to migrate).

---

## 2. Connection and environment

- The backend connects with a standard Postgres connection string. It does **not** need the Supabase anon or service key unless Supabase Auth or Storage is added later.
- Two connection strings:
  - `DATABASE_URL_DIRECT`: direct or session-mode connection. Used by Alembic migrations.
  - `DATABASE_URL`: pooled connection for the running app. If using Supabase's transaction pooler, disable prepared statements in the driver (for psycopg 3: `prepare_threshold=None`). Verify against current Supabase connection docs at setup.
- Enable **RLS on every table with no policies**. This blocks access through the public API and anon key. The backend's database role bypasses RLS, so it is unaffected.
- Never edit schema in the Supabase dashboard. All changes go through Alembic.

---

## 3. Enumerations

| Name | Values |
|---|---|
| `analysis_status` | `queued`, `running`, `completed`, `partial`, `failed` |
| `analysis_stage` | `planning`, `collecting`, `processing`, `analyzing`, `detecting`, `snapshotting`, `done` |
| `brand_role` | `target`, `competitor`, `suggested` |
| `source_type` | `web`, `news`, `youtube`, `forum`, `shopping` |
| `window_kind` | `baseline`, `current` |
| `content_purpose` | `collection`, `investigation` |
| `date_confidence` | `exact`, `approximate`, `unknown` |
| `sentiment` | `positive`, `neutral`, `negative` |
| `signal_kind` | `aspect_negative_spike` (MVP). `topic_surge` reserved. |
| `impact_level` | `low`, `medium`, `high` |
| `signal_status` | `detected`, `investigating`, `investigated` |
| `investigation_status` | `queued`, `running`, `completed`, `failed` |
| `investigation_step` | `generating_queries`, `collecting_evidence`, `scoring_evidence`, `comparing_competitors`, `synthesizing`, `recommending`, `done` |
| `scope_verdict` | `brand_specific`, `industry_wide`, `inconclusive`, `unknown` |
| `stance` | `supports`, `contradicts`, `neutral` |
| `priority` | `low`, `medium`, `high` |
| `llm_call_status` | `ok`, `retry`, `rate_limited`, `invalid_json`, `failed` |

Confidence label (`low` < 40, `medium` 40–69, `high` ≥ 70) is derived at read time, not stored as an enum.

---

## 4. Relationships

```text
brands ──┬─< analysis_brands >──┬── analyses
         │                      │
         │                      ├─< serp calls counted on analyses.serp_calls_used
         │                      │
         └─< content_items >────┤  (analysis_id, brand_id)
                 │              │
                 ├── content_analysis (1:1)
                 ├─< item_aspects
                 └─< evidence >── investigations >── signals ── analyses
                                       │
                                       └─< recommendations

analyses ─< brand_snapshots (per brand)
analyses ─< trend_points    (per brand, keyword)
analyses ─< signals
serp_cache  (standalone, keyed by request hash)
llm_calls   (standalone log, optional FK to analysis / investigation)
```

---

## 5. Tables

Legend: **PK** primary key, **FK** foreign key, **NN** not null.

### 5.1 `brands`
| Column | Type | Notes |
|---|---|---|
| id | uuid PK | |
| name | text NN | Display name as first entered |
| normalized_name | text NN unique | Lowercased, trimmed, collapsed whitespace |
| created_at | timestamptz NN | default now() |

### 5.2 `analyses`
One row per analysis run. Product is a column here; there is no separate `products` table in the MVP.

| Column | Type | Notes |
|---|---|---|
| id | uuid PK | |
| brand_id | uuid FK → brands NN | Target brand |
| product | text | Optional, ≤ 80 chars |
| category | text | Optional. Chosen on the form (dropdown); selects aspect lexicon preset. Default `consumer_electronics`. No LLM involved. |
| period_days | smallint NN | 7, 14 or 30. Default 30. |
| as_of_date | date NN | End of the current window. Defaults to today; **pinned** for the demo so window dates, and therefore cache keys, are stable. |
| current_start / current_end | date NN | Current window |
| baseline_start / baseline_end | date NN | Preceding equal-length window |
| status | analysis_status NN | default `queued` |
| stage | analysis_stage | Null until running |
| progress | smallint NN | 0–100 |
| warnings | jsonb NN | Array of `{code, message, stage}`. default `[]`. |
| serp_calls_used | int NN | default 0 |
| serp_calls_budget | int NN | Snapshot of config at creation (default 12) |
| live_run | boolean NN | True if at least one new (credit-spending) SerpApi call was needed |
| error | text | Set when `failed` |
| client_ip_hash | text | Salted hash, for per-IP rate limiting only (the daily cap is global, counted from `created_at`) |
| created_at | timestamptz NN | |
| started_at / finished_at | timestamptz | |

Indexes: `(created_at desc)`, `(client_ip_hash, created_at)`, `(status)`.

### 5.3 `analysis_brands`
Target and competitors for one analysis. Replaces a separate `competitors` table.

| Column | Type | Notes |
|---|---|---|
| analysis_id | uuid FK NN | |
| brand_id | uuid FK NN | |
| role | brand_role NN | `suggested` = LLM-proposed, user did not enter it |

PK `(analysis_id, brand_id)`. Check: exactly one `target` per analysis (enforce in app and with a partial unique index on `(analysis_id) where role = 'target'`).

### 5.4 `serp_cache`
Raw SerpApi responses. Replaces Redis for caching.

| Column | Type | Notes |
|---|---|---|
| cache_key | text PK | Hash of engine + normalized params with **absolute** dates (API key excluded) |
| engine | text NN | |
| params | jsonb NN | Params used, for debugging |
| response | jsonb NN | Full raw response |
| http_status | smallint | Only successful (2xx) responses are cached; empty-result responses are cached with a shorter TTL |
| fetched_at | timestamptz NN | |
| expires_at | timestamptz NN | Default TTL 30 days in free-tier mode (`SERP_CACHE_TTL_HOURS=720`). Empty-result responses use a shorter TTL. Demo entries are exported with the demo bundle. |
| pinned | boolean NN | default false. Pinned rows (demo entries) never expire and are never purged |

Index: `(expires_at)` for purge. Purge skips `pinned = true`.

### 5.4a `raw_items`
Added in Phase 3.1. The canonical `RawItem` (ARCHITECTURE.md section 6) from every content engine (web, news, forums, YouTube), stored exactly as the parser returned it. Staging store between collection and `processing/`: nothing here is cleaned, canonicalised, date-parsed or deduplicated. Phase 3.2 reads these rows and writes `content_items` (5.5). Trends is a time series, not content, and never lands here.

| Column | Type | Notes |
|---|---|---|
| id | uuid PK | |
| analysis_id | uuid FK NN | `ON DELETE CASCADE` |
| brand_id | uuid FK NN | Brand the item was collected for; never cascade-deleted |
| purpose | content_purpose NN | `collection` or `investigation` |
| window | window_kind | Set for `collection`, null for `investigation` (check constraint) |
| source_type | source_type NN | |
| engine | text NN | Check: `google`, `google_news`, `google_forums`, `youtube` |
| title | text NN | Verbatim; must contain a non-whitespace character |
| url | text NN | Verbatim, NOT canonical (that is `content_items.url`); same non-blank rule |
| snippet | text | Verbatim |
| author | text | Channel, outlet or poster where available |
| published_raw | text | String as SerpApi returned it ("3 weeks ago"). Parsed in Phase 3.2 |
| published_iso | text | `iso_date` string when SerpApi gave one. Parsed in Phase 3.2 |
| position | smallint | Rank in the response, check `>= 1` |
| query | text | Query that produced the item |
| serp_cache_key | text | Trace to `serp_cache`. No foreign key: cache rows expire, raw items must outlive them |
| metadata | jsonb NN | Engine-specific extras (views, comments, authors, ...). default `{}` |
| raw_key | text NN | sha256 hex of the verbatim identifying fields (`RawItem.compute_raw_key()`). Idempotency key, not a dedupe key |
| collected_at | timestamptz NN | default `now()` |

Constraints and indexes:
- Unique index `uq_raw_items_identity` on `(analysis_id, brand_id, purpose, raw_key)`: persisting the same parsed response twice is a no-op. The same article found by two queries has different keys and stays as two rows for Phase 3.2 to merge.
- Check `purpose_window_consistent`, `engine_allowed`, `title_not_blank`, `url_not_blank`, `position_positive`, `raw_key_sha256_hex`.
- Index `(analysis_id, brand_id, window)`, `(analysis_id, source_type)`, `(serp_cache_key)`.
- `url_hash`, `content_hash` and `dup_group` are NOT here. They are normalization outputs and belong to `content_items` (Phase 3.2).

### 5.5 `content_items`
Normalized item from any SerpApi engine.

| Column | Type | Notes |
|---|---|---|
| id | uuid PK | |
| analysis_id | uuid FK NN | |
| brand_id | uuid FK NN | Brand the item was collected for |
| purpose | content_purpose NN | `collection` or `investigation` |
| window | window_kind | Null for investigation items |
| source_type | source_type NN | |
| engine | text NN | SerpApi engine name |
| url | text NN | Canonical URL |
| url_hash | text NN | |
| domain | text NN | Used for independence counting |
| title | text NN | |
| snippet | text | Main analyzable text (title + snippet are analyzed together) |
| author | text | Channel, site or poster where available |
| published_at | timestamptz | Null when unknown |
| date_confidence | date_confidence NN | |
| query | text NN | Query that produced the item |
| metadata | jsonb NN | Engine-specific extras: views, likes, position, thumbnail, price |
| content_hash | text NN | Hash of normalized title + snippet |
| dup_group | text | Hash of normalized title; items sharing it are treated as one source for independence |
| serp_cache_key | text | Trace back to raw response |
| collected_at | timestamptz NN | |

Constraints and indexes:
- Unique `(analysis_id, brand_id, content_hash)` (exact dedupe).
- Index `(analysis_id, brand_id, window)`.
- Index `(analysis_id, source_type)`.
- Index `(content_hash)` for cross-analysis NLP reuse.

Phase 3.2 implementation notes (migration `0004`):
- Filled from `raw_items` (5.4a) by the processing stage; `url` is the canonical URL, `published_at` is parsed from `raw_items.published_raw` / `published_iso`.
- `window` is null for investigation items (check `investigation_no_window`) and also for a collection item whose known date lies outside both windows: it is kept but counts in no window.
- Check `date_matches_confidence`: `published_at` is null exactly when `date_confidence = 'unknown'`.
- `query` is NOT NULL; an item with no recorded query stores `''`.
- Also checked: `engine_allowed`, non-blank `title`/`url`/`domain`, sha256-hex `url_hash`/`content_hash`/`dup_group`.
- Two lookup indexes beyond the list above: `(analysis_id, brand_id, url_hash)` (URL-level duplicate check) and `(analysis_id, dup_group)` (independence counting).
- No foreign key to `raw_items` or `serp_cache` (`serp_cache_key` is a trace pointer).

### 5.6 `content_analysis`
One row per item; output of the local NLP pipeline.

| Column | Type | Notes |
|---|---|---|
| content_id | uuid PK FK → content_items | |
| content_hash | text NN | Copied for reuse lookup |
| sentiment | sentiment NN | Overall item sentiment (low-margin predictions become `neutral`) |
| sentiment_score | real NN | −1.0 to 1.0, derived from model class probabilities |
| negative_prob | real NN | Model probability of the negative class; feeds signal component S |
| is_about_brand | boolean NN | Rule-based relevance. False items are excluded from all counts. |
| matched_terms | text[] NN | Brand, product or alias terms that matched |
| topics | text[] NN | |
| keywords | text[] NN | |
| model | text NN | Hugging Face model id used |
| analyzer_version | text NN | Model + lexicon version + rule version. Any change invalidates reuse. |
| analyzed_at | timestamptz NN | |

Index: `(content_hash, analyzer_version)`. Before running inference, look up this index and copy results for items already analyzed (zero inference on re-runs).

Phase 4.2 implementation notes (migration `0005`, model `ContentAnalysisRow`, `ContentAnalysisRepository`):
- `content_id` is the PK and a foreign key to `content_items` with ON DELETE CASCADE, so deleting an analysis removes its NLP rows through its content items.
- `sentiment_score`, `negative_prob` are `real` (float4) as documented; stored values carry float4 precision.
- `matched_terms`, `topics`, `keywords` default to `'{}'`. `topics` and `keywords` are filled by `services/nlp/keywords.py` and `topics.py` (Phase 4.3: per-text frequency keywords, topics = aspects plus uncovered keywords); they are empty for items that are not about the brand.
- Checks: score in [-1, 1], probability in [0, 1], sha256-hex `content_hash`, non-blank `model` and `analyzer_version`. The `(content_hash, analyzer_version)` index is not unique (the same text can be analyzed in several analyses).
- `analyzer_version` = `model|lexicon|clause rules|relevance rules|keyword rules|topic rules|category[|config tag]` (`services/nlp/analyzer_version.py`). The category and the sentiment config tag (neutral margin, max length) are part of it because they change the results.
- Reuse copies only model-derived results (sentiment, scores, topics, keywords, model, aspects, original `analyzed_at`). Relevance is brand-specific, so a reused row takes the caller's `matched_terms` and is `is_about_brand = true`. Only sources with `is_about_brand = true` are reusable: items that are not about the brand never went through inference and get a neutral row.
- Rows are never overwritten; an item that already has a row is skipped.

### 5.7 `item_aspects`
One row per item-aspect pair.

| Column | Type | Notes |
|---|---|---|
| content_id | uuid FK NN | |
| aspect | text NN | From the lexicon preset, e.g. `battery`, `camera` |
| clause | text NN | The clause that was analyzed. Shown in the UI as the evidence snippet. |
| sentiment | sentiment NN | Sentiment of the clause |
| negative_prob | real NN | Negative-class probability for the clause |
| score | real NN | −1.0 to 1.0 |

PK `(content_id, aspect)`. Index `(aspect, sentiment)`.

Phase 4.2 implementation notes (migration `0005`, model `ItemAspectRow`, `ItemAspectRepository`):
- `content_id` is a foreign key to `content_items` with ON DELETE CASCADE (not to `content_analysis`).
- `negative_prob` and `score` are `real`; checks keep them in [0, 1] and [-1, 1]; `aspect` and `clause` must be non-blank.
- Written together with the item's `content_analysis` row in one transaction (`ContentAnalysisRepository.save_many`).

### 5.8 `trend_points`
Google Trends timeseries.

| Column | Type | Notes |
|---|---|---|
| id | bigserial PK | |
| analysis_id | uuid FK NN | |
| brand_id | uuid FK NN | |
| keyword | text NN | Brand name, or "brand + aspect" for investigation checks |
| date | date NN | |
| value | smallint NN | 0–100 relative interest |

Unique `(analysis_id, brand_id, keyword, date)`.

### 5.9 `brand_snapshots`
Computed aggregates, one row per brand per analysis. Powers the dashboard and the competitor table.

| Column | Type | Notes |
|---|---|---|
| analysis_id | uuid FK NN | |
| brand_id | uuid FK NN | |
| sample_size | int NN | Items in the current window that count (`is_about_brand`) |
| baseline_sample_size | int NN | |
| sentiment_dist | jsonb NN | `{positive, neutral, negative}` as percentages |
| aspect_scores | jsonb NN | Array of `{aspect, net_score, mentions, positive, neutral, negative}` |
| topic_counts | jsonb NN | |
| source_mix | jsonb NN | Counts per `source_type` |
| health | jsonb NN | `{overall, sentiment, engagement, risk, trend, formula_version}` |
| interest_change_pct | real | Search-interest change, current vs baseline |
| low_data | boolean NN | True when below minimum sample guard |
| created_at | timestamptz NN | |

PK `(analysis_id, brand_id)`.

### 5.10 `signals`
Detected emerging signals.

| Column | Type | Notes |
|---|---|---|
| id | uuid PK | |
| analysis_id | uuid FK NN | |
| brand_id | uuid FK NN | |
| kind | signal_kind NN | |
| aspect | text NN | |
| baseline_n / baseline_total | int NN | Aspect-negative mentions and total items, baseline window |
| current_n / current_total | int NN | Same, current window |
| baseline_share / current_share | real NN | |
| growth | real NN | Normalized growth multiple |
| components | jsonb NN | `{growth, frequency, cross_source, sentiment_impact}` each 0–1 |
| signal_score | real NN | 0–1 |
| impact | impact_level NN | |
| signal_confidence | smallint NN | 0–100, pre-investigation |
| sources_count | smallint NN | |
| source_types | text[] NN | |
| trend_corroborated | boolean | Search interest moved the same way |
| status | signal_status NN | default `detected` |
| created_at | timestamptz NN | |

Unique `(analysis_id, brand_id, kind, aspect)`. Index `(analysis_id, signal_score desc)`.

### 5.11 `investigations`
One investigation run per signal (re-runs create new rows).

| Column | Type | Notes |
|---|---|---|
| id | uuid PK | |
| signal_id | uuid FK NN | |
| status | investigation_status NN | |
| step | investigation_step | |
| queries | jsonb NN | Array of `{hypothesis, engine, query}` |
| summary | text | Plain-language explanation |
| findings | jsonb NN | Array of `{text, evidence_ids}`. IDs validated against `evidence`. |
| scope | scope_verdict | |
| scope_ratio | real | Brand share ÷ median competitor share |
| confidence | smallint | 0–100, formula output |
| confidence_factors | jsonb | `{independence, agreement, signal_strength, recency, consistency}` each 0–1 |
| competitor_comparison | jsonb | Rows per brand for the signal's aspect |
| serp_calls_used | int NN | |
| generated_by | text | `llm` or `fallback` (template report when Groq quota or errors prevent LLM output) |
| llm_model | text | |
| error | text | |
| created_at, started_at, finished_at | timestamptz | |

Partial unique index: one active (`queued` or `running`) investigation per `signal_id`. Index `(signal_id, created_at desc)`; "latest" = newest row.

### 5.12 `evidence`
Links an investigation to supporting, contradicting or neutral content items.

| Column | Type | Notes |
|---|---|---|
| id | uuid PK | |
| investigation_id | uuid FK NN | |
| signal_id | uuid FK NN | Denormalized for fast lookup |
| content_item_id | uuid FK NN | |
| stance | stance NN | |
| relevance | real NN | 0–1 |
| note | text | One-line relation to the finding |
| rank | smallint NN | Display order |
| created_at | timestamptz NN | |

Unique `(investigation_id, content_item_id)`.

### 5.13 `recommendations`
| Column | Type | Notes |
|---|---|---|
| id | uuid PK | |
| investigation_id | uuid FK NN | |
| priority | priority NN | Derived from signal impact and confidence |
| title | text NN | |
| action | text NN | |
| rationale | text NN | |
| evidence_ids | uuid[] NN | Must be non-empty and valid |
| timeframe | text | e.g. "next 7 days" |
| position | smallint NN | |

### 5.14 `llm_calls`
Debug and quota log for Groq (free tier). Prompts and completions are **not** stored by default. Used to enforce `LLM_MAX_CALLS_PER_INVESTIGATION` and to see rate-limit hits.

| Column | Type | Notes |
|---|---|---|
| id | bigserial PK | |
| analysis_id | uuid | Nullable FK |
| investigation_id | uuid | Nullable. Plain column in Phase 6; FK added in the Phase 7 migration |
| task | text NN | `suggest_competitors`, `generate_queries`, `tag_stance`, `synthesize`, `recommend`. NLP is local and is not logged here. |
| provider | text NN | default `groq` |
| model | text NN | |
| prompt_version | text NN | |
| attempt | smallint NN | |
| tokens_in / tokens_out | int | |
| latency_ms | int | |
| status | llm_call_status NN | |
| error | text | |
| created_at | timestamptz NN | |

### 5.15 `serp_usage`
One row per SerpApi request attempt. The monthly counter (250 on the free plan) is derived from this table.

| Column | Type | Notes |
|---|---|---|
| id | bigserial PK | |
| cache_key | text NN | |
| engine | text NN | |
| cache_hit | boolean NN | Hits cost no credit |
| credits | smallint NN | 1 for a live successful call, 0 otherwise |
| http_status | smallint | |
| analysis_id | uuid | Nullable FK |
| investigation_id | uuid | Nullable. Plain column in Phase 2; FK to `investigations` added in the Phase 7 migration |
| purpose | text NN | `analysis`, `investigation`, `fixture_recording`, `probe` |
| account_label | text NN | Value of `SERPAPI_ACCOUNT_LABEL` when the call was made |
| created_at | timestamptz NN | |

Monthly used = `sum(credits)` for the current calendar month where `account_label` = current `SERPAPI_ACCOUNT_LABEL`. Switching to a new SerpApi account (new key + new label) starts a clean count. Index `(created_at)`.


---

## 6. Data lifecycle by stage

| Stage | Writes |
|---|---|
| POST /analyses | `brands`, `analyses` (queued), `analysis_brands` |
| planning | windows from `as_of_date`, budget; `analysis_brands` rows with `suggested` role if no competitors given (one Groq call, logged in `llm_calls`) |
| collecting | `serp_cache`, `serp_usage`, `raw_items` (parsed results; wired in Phase 6), `trend_points`, `analyses.serp_calls_used`, `analyses.live_run` |
| processing | reads `raw_items`; writes `content_items` (after clean, normalize, dedupe) |
| analyzing | `content_analysis`, `item_aspects` (local model, no network) |
| detecting | `signals` |
| snapshotting | `brand_snapshots` (target and each competitor) |
| done | `analyses.status`, `finished_at` |
| Investigate | `investigations`, `content_items` (purpose = investigation), `serp_usage`, `content_analysis` where needed, `evidence`, `trend_points`, `recommendations`, `llm_calls`; `signals.status` updated |

All writes within one stage happen in one transaction where practical. A failed stage leaves earlier stages' data intact so `partial` results are usable.

---

## 7. Aggregation rules (how numbers are computed)

- **Counted items:** `content_items` joined to `content_analysis` where `is_about_brand = true`, within the analysis and brand.
- **Growth sources:** `source_type` in (`news`, `web`) with `date_confidence` in (`exact`, `approximate`) and a window assigned. Growth shares use only these. Other source types count toward frequency, cross-source and corroboration.
- **Window totals (N):** counted items per `window` (per source group as above).
- **Aspect-negative count (n):** counted items having an `item_aspects` row for the aspect with `sentiment = negative`, per window.
- **Net score:** `positive% − negative%` of an aspect's mentions (−100 to 100).
- **Share:** `n / N` per window. Growth, scores and verdicts follow `docs/SCORING.md`.
- **Independence for evidence:** distinct `dup_group` within distinct `domain` among `supports` evidence.
- **Source coverage:** distinct `source_type` among supporting evidence.
- Investigation items are never counted toward window totals. Filter by `purpose = 'collection'`.

---

## 8. Retention and cleanup

- `serp_cache`: purge rows past `expires_at` with a startup or manual script. Never purge `pinned` rows.
- `analyses` and children: keep. Add a manual cleanup script that deletes an analysis and its dependents (`ON DELETE CASCADE` from `analyses`).
- `llm_calls`: keep for the MVP; trim by age later if needed.
- Foreign keys from `analyses` children use `ON DELETE CASCADE`. `brands` rows are never cascade-deleted.

---

## 9. Migration plan (aligned with development phases)

| Phase | Migration adds |
|---|---|
| 0 | extensions (`pgcrypto` if needed), enums, `brands`, `analyses`, `analysis_brands` |
| 2 | `serp_cache` (with `pinned`), `serp_usage` (with `account_label`; `investigation_id` as plain column) |
| 3.1 | `raw_items` (migration `0003`) |
| 3.2 | `content_items` (migration `0004`) |
| 4.2 | `content_analysis`, `item_aspects` (migration `0005`) |
| 5 | `trend_points`, `brand_snapshots`, `signals` |
| 6 | `llm_calls` (`investigation_id` as plain column) |
| 7 | `investigations`, `evidence`, plus FKs from `serp_usage.investigation_id` and `llm_calls.investigation_id` |
| 8 | `recommendations` |

Rules:
- One migration per group; descriptive names.
- Test `alembic upgrade head` on a blank database in CI.
- Do not edit a merged migration; add a new one.
- Downgrades are optional for the MVP.

---

## 10. Seed and golden data

- `scripts/seed_demo.py` (built in Phase 6) loads `contracts/golden/samsung_battery.json` (synthetic) into the tables with fixed IDs, so the `demo` analysis works from a real database.
- `scripts/export_demo_bundle.py` (Phase 10) exports a real analysis, its investigation and the related `serp_cache` rows to `contracts/demo/samsung_s25_ultra.json`. The bundle can be re-imported after a database reset or served directly in `DEMO_MODE`, with no database, model or network.
- The golden fixture must be consistent with this schema: same field names, enums and ranges as the API DTOs in `API.md`.

---

## 11. Additions and changes in v2

- `analyses.as_of_date` (pinned windows, stable cache keys), `analyses.live_run`.
- `analyses.category` now comes from a form dropdown, not an LLM.
- New table `serp_usage` for the monthly SerpApi counter.
- `content_analysis`: `analyzer_version` replaces `prompt_version`; `relevance` replaced by rule-based `matched_terms`; added `negative_prob`.
- `item_aspects`: added `clause` and `negative_prob`.
- `llm_calls` migration moves from Phase 4 to Phase 6 (first Groq use is competitor suggestion in the analysis pipeline).
- Earlier additions retained: `serp_calls_budget`, `client_ip_hash`, `content_items.dup_group`, `serp_cache_key`, `brand_snapshots.sample_size / baseline_sample_size / low_data / source_mix`, `signals.trend_corroborated`, structured `investigations.summary` and `findings`, `scope_ratio`.
- Add to `investigations`: `generated_by` (`llm` or `fallback`), so the UI can mark template-generated reports.

## 12. Additions in v2.1

- `serp_cache.pinned` (demo cache never expires or purges).
- `serp_usage.account_label` (clean monthly count when switching SerpApi accounts).
- `serp_usage.investigation_id` and `llm_calls.investigation_id` are plain columns until the Phase 7 migration adds the FKs.
- Daily analysis cap is global; `client_ip_hash` used for per-IP rate limiting only.
- `net_score` defined as `positive% − negative%`.
- Max 2 competitors per analysis.