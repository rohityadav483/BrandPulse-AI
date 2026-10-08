# BrandPulse AI: API Specification (v2)

**v2 changes:** live runs are quota-aware (`estimateAnalysis`, `getUsage`, `X-Access-Code`, new error codes); mentions carry the analyzed `clause`; reports carry `generated_by`; health reports NLP model status; example sample sizes are realistic for the free SerpApi plan.

Backend: FastAPI. Base path: `/api/v1`. Format: JSON. The OpenAPI document exported from FastAPI (`contracts/openapi.json`) is the machine-readable source of truth; frontend types are generated from it. This file defines intent, shapes and rules.

---

## 1. Conventions

| Topic | Rule |
|---|---|
| Auth | No user accounts in the MVP. Resources are addressed by unguessable UUIDs. **Live runs** (those that would spend new SerpApi credits) require the `X-Access-Code` header matching `LIVE_ACCESS_CODE`. Cached-only runs and all reads need no code. If `LIVE_ACCESS_CODE` is unset the check is disabled (local-only use). |
| IDs | UUID strings. Demo aliases (`demo`, `demo-signal-battery`, `demo-investigation`) are accepted in path parameters when `DEMO_MODE=true`. |
| Timestamps | ISO 8601 UTC strings. |
| Casing | `snake_case` in JSON. |
| Enums | Lowercase strings; values defined in `DATABASE.md` §3. |
| Percentages | Numbers 0–100, not fractions, unless a field name ends in `_share` (fraction 0–1). |
| Scores | Computed server-side only. The frontend formats, never calculates. |
| Pagination | `page` (1-based), `page_size` (default 20, max 100). Response includes `total`. Exception: `listAnalyses` uses `limit` only. |
| Long jobs | `202 Accepted`. Client polls the status resource every 2 s and stops on a terminal state. |
| Proxying | Next.js rewrites `/api/*` to FastAPI, so the browser calls same-origin. CORS stays as a fallback. |
| Operation IDs | Stable camelCase IDs so generated TS client names do not drift. |

### Error envelope

All non-2xx responses:

```json
{
  "error": {
    "code": "analysis_not_ready",
    "message": "Analysis is still running.",
    "details": { "status": "running", "stage": "analyzing" }
  }
}
```

| HTTP | `code` | When |
|---|---|---|
| 400 | `bad_request` | Malformed body |
| 404 | `not_found` | Unknown or deleted ID |
| 409 | `analysis_not_ready` | Dashboard requested before `completed` or `partial` |
| 409 | `analysis_failed` | Dashboard requested for a failed analysis (`details.error` included) |
| 409 | `signal_not_investigable` | Signal belongs to an analysis that is not usable |
| 409 | `investigation_in_progress` | `force=true` while an investigation for the signal is queued or running |
| 422 | `validation_error` | Field validation failed (`details.fields`) |
| 429 | `daily_limit_reached` | Global daily analysis cap hit (protects SerpApi and Groq quota) |
| 429 | `rate_limited` | Per-IP rate limit hit; `Retry-After` header set |
| 403 | `live_access_required` | Run needs new SerpApi calls and `X-Access-Code` is missing or wrong |
| 429 | `serpapi_quota_low` | Remaining monthly searches would fall below the reserve (`details.remaining`, `details.reserve`) |
| 409 | `live_data_disabled` | `ALLOW_LIVE_SERPAPI` is off and the run needs uncached data |
| 503 | `nlp_unavailable` | Local NLP model failed to load |
| 500 | `internal_error` | Unexpected. Never leaks internals. |
| 503 | `service_unavailable` | Database unreachable |

---

## 2. Shared types

### Warning
```json
{ "code": "serpapi_engine_failed", "message": "Google Forums returned no usable results.", "stage": "collecting" }
```
Known codes: `serpapi_engine_failed`, `serpapi_budget_exhausted`, `low_data`, `date_coverage_low`, `llm_step_failed`, `competitor_data_thin`, `live_data_disabled`.

### BrandRef
```json
{ "id": "uuid", "name": "Samsung", "role": "target" }
```

### Period
```json
{ "current_start": "2026-09-06", "current_end": "2026-10-05", "baseline_start": "2026-08-07", "baseline_end": "2026-09-05" }
```

### Source
```json
{
  "source_type": "forum",
  "domain": "reddit.com",
  "url": "https://...",
  "title": "…",
  "snippet": "…",
  "author": "…",
  "published_at": "2026-10-01T08:00:00Z",
  "date_confidence": "exact",
  "collected_at": "2026-10-06T09:12:00Z"
}
```

---

## 3. Endpoints

| Operation ID | Method + path | Purpose |
|---|---|---|
| `estimateAnalysis` | `POST /analyses/estimate` | Cost preview; no side effects |
| `createAnalysis` | `POST /analyses` | Start an analysis |
| `listAnalyses` | `GET /analyses` | Recent analyses |
| `getAnalysis` | `GET /analyses/{id}` | Status, stage, progress |
| `getDashboard` | `GET /analyses/{id}/dashboard` | Full dashboard payload |
| `listMentions` | `GET /analyses/{id}/mentions` | Source items behind an aspect or sentiment |
| `getSignal` | `GET /signals/{id}` | Signal detail |
| `investigateSignal` | `POST /signals/{id}/investigate` | Start or reuse an investigation |
| `getInvestigation` | `GET /investigations/{id}` | Status, then full report |
| `listInvestigationEvidence` | `GET /investigations/{id}/evidence` | Evidence explorer |
| `getUsage` | `GET /usage` | Monthly SerpApi and daily Groq/analysis usage |
| `getHealth` | `GET /health` | Liveness and config check |

---

### 3.1 `POST /analyses`

Start an analysis. Returns immediately; work runs in the background.

Request:
```json
{
  "brand": "Samsung",
  "product": "Galaxy S25 Ultra",
  "competitors": ["Apple", "OnePlus"],
  "category": "consumer_electronics",
  "period_days": 30
}
```

| Field | Rules |
|---|---|
| `brand` | Required, 1–80 chars after trim |
| `product` | Optional, ≤ 80 chars |
| `competitors` | Optional, ≤ 2 items, each 1–80 chars. Case-insensitive duplicates and the target brand are removed. If empty, up to 2 suggested competitors are generated. More than 2 → `422 validation_error`. |
| `period_days` | Optional, one of 7, 14, 30. Default 30. |
| `category` | Optional, aspect lexicon preset: `consumer_electronics` (default) or `generic`. |
| `as_of_date` | Optional ISO date, end of the current window. Honored in `DEMO_MODE`, with a valid access code, or when `LIVE_ACCESS_CODE` is unset (local use); otherwise the server uses today. Pinning makes cache keys stable. |

Response `202`:
```json
{ "id": "uuid", "status": "queued", "poll_url": "/api/v1/analyses/uuid" }
```
Headers: `X-Access-Code` (required only when the run needs new SerpApi calls).

Errors: `422 validation_error`, `403 live_access_required`, `409 live_data_disabled`, `429 daily_limit_reached`, `429 rate_limited`, `429 serpapi_quota_low`, `503 nlp_unavailable`.

Tip: call `estimateAnalysis` first. If `estimated_new_calls` is 0, the run is served from cache and costs nothing.

---

### 3.2 `GET /analyses`

Query: `limit` (default 10, max 50).

Response `200`:
```json
{
  "items": [
    {
      "id": "uuid",
      "brand": "Samsung",
      "product": "Galaxy S25 Ultra",
      "status": "completed",
      "created_at": "2026-10-06T09:10:00Z",
      "top_signal": { "aspect": "battery", "impact": "high" }
    }
  ]
}
```
`top_signal` is null when none was detected.

---

### 3.3 `GET /analyses/{id}`

Lightweight status. Poll this.

Response `200`:
```json
{
  "id": "uuid",
  "status": "running",
  "stage": "analyzing",
  "progress": 62,
  "brands": [
    { "id": "uuid", "name": "Samsung", "role": "target" },
    { "id": "uuid", "name": "Apple", "role": "competitor" }
  ],
  "product": "Galaxy S25 Ultra",
  "period": { "current_start": "2026-09-06", "current_end": "2026-10-05", "baseline_start": "2026-08-07", "baseline_end": "2026-09-05" },
  "warnings": [],
  "serp_calls_used": 7,
  "serp_calls_budget": 12,
  "error": null,
  "created_at": "2026-10-06T09:10:00Z",
  "finished_at": null
}
```

Stage → progress guide:

| Stage | Progress range |
|---|---|
| `planning` | 0–5 |
| `collecting` | 5–40 |
| `processing` | 40–50 |
| `analyzing` | 50–85 |
| `detecting` | 85–92 |
| `snapshotting` | 92–99 |
| `done` | 100 |

Terminal states: `completed`, `partial`, `failed`.

---

### 3.4 `GET /analyses/{id}/dashboard`

Everything the overview page needs. `409 analysis_not_ready` while `queued` or `running`. Allowed for `completed` and `partial`.

Response `200` (trimmed example):
```json
{
  "analysis": { "id": "uuid", "status": "completed", "product": "Galaxy S25 Ultra", "as_of_date": "2026-08-10", "live_run": false, "period": { "...": "..." }, "warnings": [] },
  "target": {
    "brand": { "id": "uuid", "name": "Samsung", "role": "target" },
    "sample_size": 64,
    "baseline_sample_size": 41,
    "growth_sample_size": { "current": 31, "baseline": 27 },
    "low_data": false,
    "health": { "overall": 73, "sentiment": 72, "engagement": 81, "risk": 64, "trend": 76, "formula_version": "v1" },
    "sentiment": { "positive": 62, "neutral": 21, "negative": 17 },
    "aspects": [
      { "aspect": "camera", "net_score": 70, "mentions": 12, "positive": 78, "neutral": 14, "negative": 8 },
      { "aspect": "battery", "net_score": -48, "mentions": 14, "positive": 12, "neutral": 28, "negative": 60 }
    ],
    "topics": [ { "topic": "battery", "count": 14 }, { "topic": "camera", "count": 12 } ],
    "source_mix": { "web": 18, "news": 16, "youtube": 20, "forum": 10 },
    "search_interest": { "change_pct": 31, "series": [ { "date": "2026-09-06", "value": 52 } ] }
  },
  "competitors": [
    {
      "brand": { "id": "uuid", "name": "Apple", "role": "competitor" },
      "sample_size": 38,
      "low_data": false,
      "sentiment": { "positive": 74, "neutral": 15, "negative": 11 },
      "aspects": [ { "aspect": "battery", "net_score": 20, "mentions": 18, "positive": 40, "neutral": 40, "negative": 20 } ],
      "search_interest": { "change_pct": 8, "series": [] }
    }
  ],
  "signals": [
    {
      "id": "uuid",
      "brand_id": "uuid",
      "kind": "aspect_negative_spike",
      "aspect": "battery",
      "growth": 3.3,
      "impact": "high",
      "confidence": 87,
      "confidence_source": "signal",
      "sources_count": 4,
      "source_types": ["youtube", "forum", "web", "news"],
      "current_share": 0.29,
      "baseline_share": 0.07,
      "current_n": 9,
      "baseline_n": 2,
      "trend_corroborated": true,
      "status": "detected",
      "investigation_id": null
    }
  ]
}
```

Notes:
- `signals` sorted by score descending. The first is the dashboard's emerging-signal card.
- `confidence_source` is `signal` before investigation and `investigation` after, and `confidence` reflects the matching value. The UI shows one number.
- `health.engagement` is a proxy; the UI marks it lower confidence.
- `net_score` = `positive% − negative%` (−100 to 100).
- Samples are small on the free SerpApi plan. `sample_size`, `baseline_sample_size` and `growth_sample_size` are always returned and always displayed next to scores and signals.
- `growth_sample_size` counts only growth sources (news and web with reliable dates). YouTube and forum items are counted in `sample_size` but do not drive growth.
- If `low_data` is true, the UI shows a low-sample warning and no signals are produced for that brand.
- Competitor blocks are current-window snapshots only (no baseline).
- Competitor blocks omit `health` and `topics` in the MVP.

---

### 3.5 `GET /analyses/{id}/mentions`

Source items behind a number. Powers aspect click-through and the evidence explorer's "all mentions" view.

Query params:

| Param | Meaning |
|---|---|
| `brand_id` | Default: target brand |
| `aspect` | e.g. `battery` |
| `sentiment` | `positive`, `neutral`, `negative` |
| `source_type` | one of the enum |
| `window` | `baseline` or `current` (default `current`) |
| `page`, `page_size` | Pagination |

Sorted by `published_at` descending (nulls last). Each aspect entry includes the analyzed `clause`, so the UI can show exactly which text produced the sentiment.

Response `200`:
```json
{
  "items": [
    {
      "id": "uuid",
      "source": { "source_type": "youtube", "domain": "youtube.com", "url": "https://...", "title": "…", "snippet": "…", "author": "…", "published_at": "2026-10-02T10:00:00Z", "date_confidence": "approximate", "collected_at": "2026-10-06T09:11:00Z" },
      "sentiment": "negative",
      "aspects": [ { "aspect": "battery", "sentiment": "negative", "clause": "battery life is terrible since the update" } ]
    }
  ],
  "page": 1,
  "page_size": 20,
  "total": 14
}
```

---

### 3.6 `GET /signals/{id}`

Same shape as one entry of `signals` in the dashboard, plus:

```json
{
  "id": "uuid",
  "analysis_id": "uuid",
  "brand": { "id": "uuid", "name": "Samsung", "role": "target" },
  "kind": "aspect_negative_spike",
  "aspect": "battery",
  "growth": 3.3,
  "impact": "high",
  "confidence": 87,
  "confidence_source": "signal",
  "score": 0.79,
  "score_components": { "growth": 0.74, "frequency": 0.8, "cross_source": 1.0, "sentiment_impact": 0.6 },
  "sources_count": 4,
  "source_types": ["youtube", "forum", "web", "news"],
  "current_share": 0.29,
  "baseline_share": 0.07,
  "current_n": 9,
  "baseline_n": 2,
  "trend_corroborated": true,
  "status": "detected",
  "latest_investigation": null
}
```
`latest_investigation` is `{ "id": "uuid", "status": "completed" }` when one exists.

---

### 3.7 `POST /signals/{id}/investigate`

Start an investigation, or reuse one. **Idempotent by default** so double-clicks cannot burn credits.

Query: `force` (boolean, default false). `force=true` starts a new investigation even if a completed one exists. It is rejected with `409 investigation_in_progress` while another is running.

Behavior:
- No investigation exists → create, return `202`.
- One is `queued` or `running` → return it with `200`, `reused: true`.
- A `completed` one exists and `force` is false → return it with `200`, `reused: true`.

Response:
```json
{ "investigation_id": "uuid", "status": "queued", "reused": false, "poll_url": "/api/v1/investigations/uuid" }
```
Headers: `X-Access-Code` (required for live runs when live SerpApi access is enabled).

Errors: `404 not_found`, `403 live_access_required`, `409 signal_not_investigable`, `409 investigation_in_progress`, `409 live_data_disabled`, `429 rate_limited`, `429 serpapi_quota_low`.

---

### 3.8 `GET /investigations/{id}`

Poll while `queued` or `running`. The `report` field is null until `completed`.

Response `200`, in progress:
```json
{
  "id": "uuid",
  "signal_id": "uuid",
  "analysis_id": "uuid",
  "status": "running",
  "step": "collecting_evidence",
  "steps": [
    { "key": "generating_queries", "label": "Generating investigation queries", "state": "done" },
    { "key": "collecting_evidence", "label": "Collecting independent evidence", "state": "active" },
    { "key": "scoring_evidence", "label": "Cross-checking sources", "state": "pending" },
    { "key": "comparing_competitors", "label": "Comparing competitors", "state": "pending" },
    { "key": "synthesizing", "label": "Writing explanation", "state": "pending" },
    { "key": "recommending", "label": "Preparing recommendations", "state": "pending" }
  ],
  "report": null,
  "error": null
}
```

Response `200`, completed (`report` populated):
```json
{
  "id": "uuid",
  "status": "completed",
  "step": "done",
  "report": {
    "generated_by": "llm",
    "summary": "The rise in battery complaints appears to be associated with recent software changes.",
    "findings": [
      { "text": "Multiple forum threads report faster battery drain after the latest update.", "evidence_ids": ["uuid", "uuid"] },
      { "text": "News coverage mentions battery drain reports following the update.", "evidence_ids": ["uuid"] }
    ],
    "scope": {
      "verdict": "brand_specific",
      "ratio": 2.4,
      "explanation": "Samsung's battery-negative share is 2.4× the competitor median."
    },
    "confidence": {
      "score": 86,
      "label": "high",
      "factors": { "independence": 0.9, "agreement": 0.85, "signal_strength": 0.79, "recency": 0.9, "consistency": 0.8 }
    },
    "source_coverage": [
      { "source_type": "youtube", "supporting": 5 },
      { "source_type": "forum", "supporting": 7 },
      { "source_type": "web", "supporting": 3 },
      { "source_type": "news", "supporting": 2 },
      { "source_type": "trends", "supporting": 1 }
    ],
    "search_interest": { "keyword": "Samsung battery", "change_pct": 31 },
    "competitor_comparison": {
      "aspect": "battery",
      "rows": [
        { "brand": { "id": "uuid", "name": "Samsung", "role": "target" }, "positive_pct": 62, "negative_pct": 17, "aspect_negative_share": 0.28, "level": "high", "search_interest_change_pct": 31 },
        { "brand": { "id": "uuid", "name": "Apple", "role": "competitor" }, "positive_pct": 74, "negative_pct": 11, "aspect_negative_share": 0.06, "level": "low", "search_interest_change_pct": 8 }
      ]
    },
    "recommendations": [
      {
        "id": "uuid",
        "priority": "high",
        "title": "Investigate battery performance after the latest software update",
        "action": "…",
        "rationale": "…",
        "evidence_ids": ["uuid", "uuid"],
        "timeframe": "next 7 days"
      }
    ],
    "disclaimer": "Confidence is an analytical estimate based on available public sources, not a statement of certainty. Findings show association, not proven causation."
  },
  "error": null
}
```

Rules:
- Every `evidence_ids` entry resolves to a row from `listInvestigationEvidence`. The backend drops findings and recommendations whose citations fail validation.
- If no usable evidence exists: `summary` states the result is inconclusive, `confidence.label` is `low`, `findings` may be empty.
- `scope.verdict` of `unknown` means competitor data was missing or thin.
- `source_coverage` includes `trends` only when search-interest corroboration exists.
- On `failed`: `report` is null, `error` is a user-safe message. Analysis data stays viewable.
- `generated_by` is `llm` or `fallback`. `fallback` means Groq quota or errors prevented LLM output, so the summary and recommendations come from deterministic templates over the same evidence. The UI must show a notice.
- An investigation spends at most `SERP_BUDGET_PER_INVESTIGATION` SerpApi calls and `LLM_MAX_CALLS_PER_INVESTIGATION` Groq calls.

---

### 3.9 `GET /investigations/{id}/evidence`

Evidence explorer. Query: `stance`, `source_type`, `page`, `page_size`.

Response `200`:
```json
{
  "items": [
    {
      "id": "uuid",
      "stance": "supports",
      "relevance": 0.91,
      "note": "Reports battery drain after the update.",
      "rank": 1,
      "source": { "source_type": "forum", "domain": "reddit.com", "url": "https://...", "title": "…", "snippet": "…", "author": "…", "published_at": "2026-10-01T08:00:00Z", "date_confidence": "exact", "collected_at": "2026-10-06T09:20:00Z" }
    }
  ],
  "page": 1,
  "page_size": 20,
  "total": 18,
  "counts": { "supports": 14, "contradicts": 2, "neutral": 2 }
}
```

---

### 3.10 `GET /health`

```json
{
  "status": "ok",
  "version": "0.1.0",
  "database": "ok",
  "nlp": "ok",
  "serpapi_configured": true,
  "live_serpapi_enabled": false,
  "groq_configured": true,
  "demo_mode": false
}
```
`nlp` is `ok`, `loading` or `unavailable`. Never returns key values. `status` is `degraded` if the database is unreachable, a required key is missing, or NLP is unavailable (except in `DEMO_MODE`, which needs no model).

---

### 3.11 `POST /analyses/estimate`

Same request body as `createAnalysis`. No side effects and no credits spent. Use it before every live run.

Response `200`:
```json
{
  "planned_calls": 11,
  "cached_calls": 4,
  "estimated_new_calls": 7,
  "as_of_date": "2026-08-10",
  "period": { "current_start": "2026-07-12", "current_end": "2026-08-10", "baseline_start": "2026-06-12", "baseline_end": "2026-07-11" },
  "serpapi": { "limit": 250, "used": 83, "remaining": 167, "reserve": 20 },
  "live_enabled": true,
  "needs_access_code": true,
  "can_run": true,
  "blocked_reason": null
}
```
`blocked_reason` is null or one of `serpapi_quota_low`, `live_data_disabled`, `daily_limit_reached`. When `estimated_new_calls` is 0, `needs_access_code` is false and the run is free.

---

### 3.12 `GET /usage`

```json
{
  "month": "2026-10",
  "serpapi": { "limit": 250, "used": 83, "remaining": 167, "reserve": 20, "live_enabled": true },
  "groq": { "configured": true, "calls_today": 6, "model": "configured-model-id" },
  "analyses_today": { "used": 1, "limit": 3 }
}
```
The UI shows a small "live searches left this month" indicator from this endpoint. It never exposes keys.

---

## 4. Behavior rules

1. **Partial results.** `partial` analyses return `200` on the dashboard with `warnings[]` explaining what is missing. The UI shows the warnings.
2. **Daily cap and rate limit.** Daily cap is global (analyses created today, default 3, `MAX_ANALYSES_PER_DAY`). In-memory per-IP rate limiter on write endpoints. Limits are config-driven.
   **Quota guard.** Live calls are refused when the remaining monthly SerpApi searches would fall below the reserve. Cached runs are always allowed.
3. **Concurrency.** At most `MAX_CONCURRENT_ANALYSES` (default 1) run at once; extra requests stay `queued`. Groq calls run one at a time.
4. **No raw upstream data.** SerpApi JSON and LLM output are never returned directly. Only normalized, validated DTOs.
5. **Citation integrity.** Any response containing an `evidence_ids` array only contains IDs that exist and belong to that investigation.
6. **Stable ordering.** Lists have deterministic sort orders defined above.
7. **Backward compatibility.** Additive changes only within `/api/v1`. Breaking changes require `/api/v2`.
8. **Demo mode** (built in Phase 6). With `DEMO_MODE=true`, alias IDs return golden fixture data from the database seed (or directly from the fixture), including the full investigation report. Used for frontend development, e2e tests and demo fallback.

---

## 5. Frontend usage map

| Screen | Calls |
|---|---|
| Analyze form | `estimateAnalysis` (confirmation dialog), then `createAnalysis` with `X-Access-Code` when needed |
| Progress page | `getAnalysis` (poll 2 s) → redirect on `completed` / `partial` |
| Dashboard overview | `getDashboard` |
| Aspect click-through drawer | `listMentions` |
| Investigate button | `investigateSignal` → navigate to signal page |
| Investigation page | `getSignal`, `getInvestigation` (poll 2 s while active) |
| Evidence explorer | `listInvestigationEvidence`, `listMentions` |
| Competitors page | `getDashboard` (competitors block), `getInvestigation` (comparison) |
| Recent analyses | `listAnalyses` |
| Usage indicator | `getUsage` |

---

## 6. Contract workflow

1. Change Pydantic schemas in `backend/app/schemas/api.py`.
2. Run `backend/scripts/export_openapi.py` → updates `contracts/openapi.json`.
3. Regenerate `frontend/lib/api/types.generated.ts` with `openapi-typescript`.
4. Update `contracts/golden/samsung_battery.json` if shapes changed.
5. CI fails if steps 2–3 leave a git diff or the golden fixture no longer validates against the schemas.