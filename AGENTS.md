# AGENTS.md: BrandPulse AI

Rules for every coding agent working in this repo. Read this first, then `docs/PROGRESS.md`.
Sources of truth: `docs/ARCHITECTURE.md` (§4 folder structure, §3 layering), `docs/DEVELOPMENT_PLAN.md`, `docs/API.md`, `docs/DATABASE.md`, `docs/PRD.md`.
If this file and a planning doc disagree, stop and ask. Do not guess.

## Project in one paragraph

Hackathon MVP. Brand-intelligence web app: collect public web signals, run local NLP, detect an emerging negative-aspect signal, investigate it with cited evidence. Modular monolith, one monorepo, one FastAPI process, one Next.js app. **Runs locally only. No hosting.**

Stack (fixed): Next.js + TypeScript + Tailwind + shadcn/ui · FastAPI · Supabase PostgreSQL (sync SQLAlchemy 2 + Alembic) · SerpApi (only external data provider, free plan, **250 searches/month**) · Groq (only LLM provider, free tier) · local BERT-family sentiment model (CPU torch).

## Working rules

1. **One phase and one module per prompt.** Never build "the whole app". Do only what the prompt asks.
2. **Read first:** this file, `docs/PROGRESS.md`, the module's README (if any), the relevant section of `docs/API.md` / `docs/DATABASE.md`, and the relevant fixture.
3. **Inspect the repo before trusting any doc.** Never assume a planned feature exists. Update `docs/PROGRESS.md` to match reality at the end of every task.
4. **Never call live SerpApi or Groq** in tests or during development. Only when the prompt explicitly says so **and** `ALLOW_LIVE_SERPAPI=true` is set. Every live SerpApi call burns a scarce monthly credit. Run the estimator first. Never retry a failed live run blindly.
5. **Never load the real NLP model in unit tests.** Use the deterministic stub `SentimentAnalyzer`. Real-model tests carry the `model` marker and are excluded from default CI. Live-call smoke tests carry the `live` marker.
6. **No new dependency without asking.** Not in `pyproject.toml`, not in `package.json`. Justify, wait for approval.
7. **No secrets in the repo.** Never commit `.env`. Only `.env.example` with placeholder values.
8. **Do not modify or delete planning docs** (`docs/*.md`) unless the prompt says so. `docs/PROGRESS.md` is the exception: keep it current.
9. **Tests ship with code**, in the same task. Run them and report real results. Never claim a test passed without running it.
10. **Report honestly.** List what was created, what was verified, what failed, what was skipped.

## Architecture rules

- **Backend is the only DB accessor.** Browser talks to FastAPI only (via Next.js `/api` rewrite).
- **Layering:** `api/` (thin routers) → `pipeline/` (orchestrators, the ONLY layer that wires services + repositories) → `services/*` (pure logic, Pydantic in / Pydantic out) → `db/repositories`.
- Services never import each other, `api/`, or DB models. Only `pipeline/` calls repositories.
- I/O lives at the edges only: serpapi client, llm client, model loader, repositories.
- Pure logic stays out of routers and repositories.
- NLP depends on the `SentimentAnalyzer` interface so tests never load the model.
- Long jobs = FastAPI `BackgroundTasks` + status columns + 2 s polling. Single worker. **No Redis, microservices, Kubernetes, queues, Docker hosting, or extra infrastructure.**
- Sync SQLAlchemy 2 + sync `httpx`. Do not introduce async DB access.

## Data and scoring rules

- **All scores come from the backend.** Frontend only formats.
- Trend math uses mention share, not raw counts. Growth uses only reliably dated sources (news, web).
- Investigation confidence is a deterministic formula. **The LLM never invents the number.**
- LLM may cite evidence IDs only. Backend validates IDs and drops uncited claims.
- Wording: "associated with", never "caused by".
- NLP is local BERT + rules. Groq only for reasoning: query generation, stance tagging, synthesis, recommendations, optional competitor suggestion.
- SerpApi cache keys use absolute window dates from a pinned `as_of_date`.
- Demo scenario: Samsung Galaxy S25 Ultra, competitors Apple + OnePlus, `as_of_date` 2026-08-10, `period_days` 30.
- English only. Max 2 competitors per analysis.

## Contract rules

- **API change → update `docs/API.md`, regenerate `contracts/openapi.json` and TS types, update `contracts/golden/samsung_battery.json`, update tests.** All in one change.
- Golden fixture must validate against Pydantic schemas and a test must recompute its formulas.
- Frontend uses the typed client; `NEXT_PUBLIC_USE_GOLDEN` switches golden vs real API.

## Frontend rules

- White background, blue primary. Colors from design tokens only.
- **Red, yellow, green only for semantic status.** No dark mode.
- Strict TypeScript. No `any` without a comment explaining why.

## SerpApi credit discipline

- `ALLOW_LIVE_SERPAPI=false` by default. On only for a planned live session, then off again.
- Env var name is `SERPAPI_API_KEY` (not `SERPAPI_KEY`). Account swap = new key + new `SERPAPI_ACCOUNT_LABEL`.
- Monthly limit 250, reserve 20. Per-analysis cap 12, per-investigation cap 8.
- Log findings from live sessions in `docs/SERPAPI_FINDINGS.md`.

## Git rules

- `main` stays runnable.
- Work on `main` for this project unless the user explicitly changes that decision.
- **Do not create branches, commit, push, or tag unless the prompt explicitly says so.**

## Definition of done (every task)

1. Done-when criteria from `docs/DEVELOPMENT_PLAN.md` met for that step.
2. Tests written and passing.
3. No live SerpApi / Groq calls and no real-model loading in default tests.
4. Module README updated (inputs, outputs, failure behavior) when a module is touched.
5. API or schema changes reflected in docs, `openapi.json`, generated types, golden fixture.
6. No secrets in the repo.
7. `docs/PROGRESS.md` reflects the actual state.
