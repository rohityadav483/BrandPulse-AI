"""`RawItem -> ContentItem` for one (analysis, brand) batch. Pure: no DB, no network.

Composes `cleaner`, `normalizer`, `dates` and `dedupe`. The pipeline stage
(`pipeline/process_raw_items.py`) reads `raw_items`, calls this, and writes `content_items`.
"""

from collections.abc import Collection, Mapping, Sequence
from datetime import datetime

from app.schemas.domain import ContentPurpose, DateConfidence, WindowKind
from app.schemas.processing import (
    ContentItem,
    DroppedRaw,
    DropReason,
    ProcessingOutcome,
    ProcessingStats,
)
from app.schemas.serp import StoredRawItem, WindowSet
from app.services.processing.cleaner import clean_text
from app.services.processing.dates import assign_window, parse_published
from app.services.processing.dedupe import dedupe
from app.services.processing.normalizer import (
    canonical_url,
    content_hash,
    extract_domain,
    url_hash,
)


def to_content_item(
    raw: StoredRawItem,
    *,
    windows: WindowSet | None,
    reference: datetime | None = None,
) -> ContentItem | DropReason:
    """Convert one raw item, or return why it cannot become a content item.

    `reference` is the moment the result was collected (relative dates are measured from it);
    it defaults to `raw.collected_at`.
    """
    title = clean_text(raw.title)
    if title is None:
        return DropReason.empty_title
    canonical = canonical_url(raw.url)
    domain = extract_domain(raw.url)
    if canonical is None or domain is None:
        return DropReason.invalid_url
    snippet = clean_text(raw.snippet)
    author = clean_text(raw.author)

    parsed = parse_published(
        raw.published_raw, raw.published_iso, reference or raw.collected_at
    )
    if raw.purpose is ContentPurpose.investigation:
        window: WindowKind | None = None  # investigation items carry no window
    else:
        window = assign_window(parsed, windows, raw.window)

    return ContentItem(
        purpose=raw.purpose,
        window=window,
        source_type=raw.source_type,
        engine=raw.engine,
        url=canonical,
        url_hash=url_hash(canonical),
        domain=domain,
        title=title,
        snippet=snippet,
        author=author,
        published_at=parsed.published_at,
        date_confidence=parsed.confidence,
        query=raw.query
        or "",  # content_items.query is NOT NULL; "" = query not recorded
        metadata=raw.metadata,
        content_hash=content_hash(title, snippet),
        serp_cache_key=raw.serp_cache_key,
        collected_at=raw.collected_at,
    )


def _stats(
    items: Sequence[ContentItem], raw_in: int, dropped: int, groups: int
) -> ProcessingStats:
    def count(predicate) -> int:
        return sum(1 for item in items if predicate(item))

    return ProcessingStats(
        raw_in=raw_in,
        kept=len(items),
        dropped=dropped,
        near_duplicate_groups=groups,
        date_exact=count(lambda i: i.date_confidence is DateConfidence.exact),
        date_approximate=count(
            lambda i: i.date_confidence is DateConfidence.approximate
        ),
        date_unknown=count(lambda i: i.date_confidence is DateConfidence.unknown),
        window_current=count(lambda i: i.window is WindowKind.current),
        window_baseline=count(lambda i: i.window is WindowKind.baseline),
        window_none=count(lambda i: i.window is None),
    )


def process_raw_items(
    raw_items: Sequence[StoredRawItem],
    *,
    windows: WindowSet | None,
    reference_times: Mapping[str, datetime] | None = None,
    known_content_hashes: Collection[str] = (),
    known_url_hashes: Collection[str] = (),
) -> ProcessingOutcome:
    """Clean, normalize, date, window-assign and dedupe one (analysis, brand) batch.

    `reference_times` maps `serp_cache_key` to the time SerpApi was actually called
    (`serp_cache.fetched_at`) so relative dates ("3 weeks ago") are measured from the right
    moment even when the results were persisted later; items without an entry use
    `collected_at`. `known_*` are hashes already stored for this analysis and brand.
    Input order is preserved in the output.
    """
    scopes = {(raw.analysis_id, raw.brand_id) for raw in raw_items}
    if len(scopes) > 1:
        raise ValueError(
            "process_raw_items handles one (analysis, brand) batch at a time"
        )

    converted: list[tuple[StoredRawItem, ContentItem]] = []
    dropped: list[DroppedRaw] = []
    references = reference_times or {}
    for raw in raw_items:
        result = to_content_item(
            raw,
            windows=windows,
            reference=references.get(raw.serp_cache_key)
            if raw.serp_cache_key
            else None,
        )
        if isinstance(result, DropReason):
            dropped.append(DroppedRaw(raw_item_id=raw.id, reason=result))
        else:
            converted.append((raw, result))

    items = [item for _, item in converted]
    deduped = dedupe(items, known_content_hashes, known_url_hashes)
    for drop in deduped.dropped:
        dropped.append(
            DroppedRaw(raw_item_id=converted[drop.index][0].id, reason=drop.reason)
        )

    kept = [
        items[index].model_copy(update={"dup_group": deduped.dup_groups[index]})
        for index in deduped.kept
    ]
    return ProcessingOutcome(
        items=kept,
        dropped=dropped,
        stats=_stats(kept, len(raw_items), len(dropped), deduped.near_duplicate_groups),
    )
