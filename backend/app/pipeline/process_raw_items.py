"""Processing stage: read `raw_items`, write `content_items` (Phase 3.2).

The only place that wires `services/processing` to the two repositories. It never touches
SerpApi: it works on rows already persisted by Phase 3.1, so it spends no credits and is safe to
re-run (hashes already stored are reported as `already_stored`, nothing is inserted twice).
Not yet called by `analysis_pipeline` (that wiring is Phase 6).
"""

import uuid
from collections.abc import Mapping
from datetime import datetime

from app.db.repositories.content_item import ContentItemRepository
from app.db.repositories.raw_item import RawItemRepository
from app.schemas.domain import ContentPurpose
from app.schemas.processing import ProcessingRunResult, ProcessingStats
from app.schemas.serp import StoredRawItem, WindowSet
from app.services.processing.processor import process_raw_items


def _add_stats(total: ProcessingStats, part: ProcessingStats) -> ProcessingStats:
    return ProcessingStats(
        **{
            name: getattr(total, name) + getattr(part, name)
            for name in ProcessingStats.model_fields
        }
    )


def process_analysis_raw_items(
    raw_repo: RawItemRepository,
    content_repo: ContentItemRepository,
    analysis_id: uuid.UUID,
    *,
    windows: WindowSet | None,
    brand_id: uuid.UUID | None = None,
    purpose: ContentPurpose | None = None,
    reference_times: Mapping[str, datetime] | None = None,
) -> ProcessingRunResult:
    """Turn the analysis' raw items into content items, one brand at a time.

    Deduplication is scoped to (analysis, brand), matching the unique index. `windows` decides
    the window of dated collection items (undated ones keep the window of the call that found
    them). `reference_times` (serp_cache_key -> time SerpApi was called) anchors relative dates;
    without it `raw_items.collected_at` is used.
    """
    raws = raw_repo.list_for_analysis(analysis_id, brand_id=brand_id, purpose=purpose)
    by_brand: dict[uuid.UUID, list[StoredRawItem]] = {}
    for raw in raws:
        by_brand.setdefault(raw.brand_id, []).append(raw)

    result = ProcessingRunResult(analysis_id=analysis_id, raw_read=len(raws))
    for brand, batch in by_brand.items():
        known_content, known_urls = content_repo.stored_hashes(analysis_id, brand)
        outcome = process_raw_items(
            batch,
            windows=windows,
            reference_times=reference_times,
            known_content_hashes=known_content,
            known_url_hashes=known_urls,
        )
        written = content_repo.add_many(analysis_id, brand, outcome.items)
        result.kept += len(outcome.items)
        result.inserted += written.inserted
        result.db_duplicates += written.duplicates
        result.dropped.extend(outcome.dropped)
        result.stats = _add_stats(result.stats, outcome.stats)
    return result
