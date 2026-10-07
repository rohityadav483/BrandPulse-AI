# BrandPulse backend

FastAPI backend and contract layer. The backend is the only database accessor.

## Phase 0 commands

```bash
pip install -e ".[dev]"
python scripts/export_openapi.py --check
python scripts/validate_golden.py
pytest
ruff check .
ruff format --check .
```

## Phase 2: SerpApi layer

Code in `app/services/serpapi/` (see its README), tables `serp_cache` and `serp_usage`
(migration `0002`). Run `alembic upgrade head` with `DATABASE_URL_DIRECT` set. Tests need no
network. DB tests run only when `TEST_DATABASE_URL` is set.

```bash
python scripts/record_serp_fixtures.py --brand Samsung --product "Galaxy S25 Ultra" --as-of 2026-08-10
```

That command is plan-only. Recording live fixtures needs `--live --confirm-credits N` plus
`ALLOW_LIVE_SERPAPI=true`.

Live SerpApi/Groq calls are disabled by default. Do not commit `.env` or any API key.

## Phase 3.1: RawItem contract and persistence

`RawItem` (`app/schemas/serp.py`) is persisted unchanged in table `raw_items` (migration `0003`, model `app/db/models/raw_item.py`) through `RawItemRepository` (`app/db/repositories/raw_item.py`: `add`, `add_many`, `get`, `list_for_analysis`, `count`, `exists`, `existing_keys`). Re-persisting the same parsed response is a no-op. No cleaning, normalization or deduplication yet: that is Phase 3.2 (`content_items`). See `app/services/serpapi/README.md` and `docs/DATABASE.md` 5.4a.

## Phase 3.2: processing and content_items

`services/processing/` (`cleaner`, `normalizer`, `dates`, `dedupe`, `processor`; see its README) turns `raw_items` into `content_items` (migration `0004`, `app/db/models/content_item.py`, `ContentItemRepository`). The stage `app/pipeline/process_raw_items.py` reads `raw_items`, processes one brand at a time and writes `content_items`; it never calls SerpApi and is safe to re-run. Not yet called from `analysis_pipeline` (Phase 6). No NLP, scoring or signals.
