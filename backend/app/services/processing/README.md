# services/processing

Phase 3.2. Turns `RawItem`s (persisted in `raw_items`, Phase 3.1) into deduplicated, dated `ContentItem`s (`content_items`). Pure functions, stdlib only, no I/O, no network, no DB. Services here never import repositories or DB models; `pipeline/process_raw_items.py` wires them.

## Inputs and outputs

| Module | In | Out |
|---|---|---|
| `cleaner.clean_text` | raw string or None | string with HTML, invisible/control characters and odd whitespace removed, or None if nothing readable is left. Never changes wording or case |
| `normalizer.canonical_url` | URL | canonical https URL (host lowercased without `www.`/`m.`/`amp.`/`mobile.`, default port and fragment dropped, tracking parameters removed, query sorted, trailing slash dropped, YouTube forms unified), or None for non-http(s)/invalid |
| `normalizer.extract_domain` | URL | host of the canonical URL (no public-suffix list: `news.x.test` and `x.test` are different domains) |
| `normalizer.url_hash` / `content_hash` | canonical URL / title + snippet | sha256 hex. `content_hash` uses `normalize_for_match` (casefold, punctuation and spacing collapsed), so it is also the NLP reuse key |
| `normalizer.title_key` | title, author | normalized title; an outlet suffix ("- Example Daily") is removed only when it equals the item's own author |
| `dates.parse_published` | `published_raw`, `published_iso`, reference time | `ParsedDate(published_at, confidence)`: `exact` (ISO, SerpApi news format, full calendar date), `approximate` ("3 weeks ago", "yesterday", date without year), `unknown` (missing, unparseable, implausible, future). Never guessed |
| `dates.assign_window` | parsed date, `WindowSet`, planned window | `current` / `baseline` by the UTC date; a known date outside both windows gives None; no usable date keeps the planned window of the call that found the item |
| `dedupe.dedupe` | `ContentItem[]` (+ known stored hashes) | kept indexes, dropped duplicates with reason, `dup_group` per kept item |
| `processor.process_raw_items` | `StoredRawItem[]` of one (analysis, brand), `WindowSet`, optional reference times and known hashes | `ProcessingOutcome(items, dropped, stats)` |

## Rules

- **Relative dates** are measured from the moment the result was collected, not from `as_of_date`. `process_raw_items(reference_times=...)` maps `serp_cache_key` to the time SerpApi was actually called (`serp_cache.fetched_at`) so cached results are anchored correctly; without an entry `raw_items.collected_at` is used. A relative month is 30 days, a year 365; numeric dates are month-first.
- **Pinned-date caveat:** with a past `as_of_date` (the demo uses 2026-08-10), relative dates from YouTube and forums are measured from the real collection time and usually fall outside both windows, so those items are kept with `window = None` and `date_confidence = approximate`. They corroborate but do not drive growth (ARCHITECTURE.md decision 7).
- **Exact duplicate** = same `content_hash` or same canonical `url_hash` (transitively) within one analysis and brand, or a hash already stored. One item is kept (best date confidence, then has a snippet, then first seen); the rest are reported in `dropped` with a `DropReason`. Nothing is dropped silently.
- **Near duplicate** = kept, but sharing a `dup_group` (sha256 of the normalized title). Same normalized title, or both titles with at least 4 words and token Jaccard >= 0.8 against the first item of an existing group (no chaining). Grouping only sees the batch it is given; a stored item with an identical normalized title still lands in the same group through its hash. No embeddings.
- **Dropped before dedupe:** `empty_title` (nothing readable after cleaning) and `invalid_url`.
- `content_items.query` is NOT NULL; a raw item with no recorded query gets `""`.

## Failure behavior

Pure functions never raise on bad data: they return None / `unknown` / a `DropReason`. `process_raw_items` raises `ValueError` only if the batch mixes analyses or brands (a caller bug). Database failures belong to the repository: a batch write is one transaction.

## Tests

`tests/unit/test_processing_*.py` (table-driven, no DB) and `tests/integration/test_process_raw_items_pipeline.py`, `test_content_item_repository.py` (PostgreSQL, skipped without `TEST_DATABASE_URL`). All use the synthetic SerpApi fixtures in `tests/fixtures/serpapi/`.
