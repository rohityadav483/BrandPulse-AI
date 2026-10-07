"""Exact-duplicate detection and near-duplicate grouping. Pure functions, no I/O.

Two different questions, two different outcomes:

- **Exact duplicate** (same `content_hash` or same canonical `url_hash`): the same item seen
  again, e.g. one page returned by two queries. Only one is kept; the rest are dropped and
  reported. The database unique index on `(analysis_id, brand_id, content_hash)` backs this up.
- **Near duplicate** (syndicated or lightly edited headline): kept, but given a shared
  `dup_group` so independence counting treats them as one source (docs/DATABASE.md 5.5).

Near-duplicate rule, no embeddings: the normalized title (outlet suffix removed when it equals
the item's author) must match exactly, or both titles need at least `MIN_FUZZY_TOKENS` words and
a token Jaccard overlap of at least `NEAR_DUPLICATE_THRESHOLD`. Each item is compared with the
first item of every existing group, never with other members, so groups cannot chain
A~B~C into one big cluster. Grouping only sees the batch it is given (stored items keep their
own `dup_group`; an identical normalized title still lands in the same group via its hash).
"""

import hashlib
from collections.abc import Collection, Sequence

from pydantic import BaseModel, Field

from app.schemas.domain import DateConfidence
from app.schemas.processing import ContentItem, DropReason
from app.services.processing.normalizer import title_key

NEAR_DUPLICATE_THRESHOLD = 0.8
MIN_FUZZY_TOKENS = 4

_DATE_RANK = {
    DateConfidence.exact: 0,
    DateConfidence.approximate: 1,
    DateConfidence.unknown: 2,
}


class DroppedDuplicate(BaseModel):
    """Index into the input sequence of an item removed as an exact duplicate, and why."""

    index: int
    reason: DropReason


class DedupeResult(BaseModel):
    """`kept`: input indexes in input order. `dup_groups`: kept index -> dup_group."""

    kept: list[int] = Field(default_factory=list)
    dropped: list[DroppedDuplicate] = Field(default_factory=list)
    dup_groups: dict[int, str] = Field(default_factory=dict)  # kept index -> dup_group
    near_duplicate_groups: int = 0


def group_id(key: str, fallback: str) -> str:
    """dup_group value: sha256 of the normalized title, or of the URL hash if the title has no
    letters or digits (so unrelated punctuation-only titles never share a group)."""
    payload = key if key else f"url:{fallback}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


class _UnionFind:
    def __init__(self, size: int) -> None:
        self._parent = list(range(size))

    def find(self, node: int) -> int:
        while self._parent[node] != node:
            self._parent[node] = self._parent[self._parent[node]]
            node = self._parent[node]
        return node

    def union(self, a: int, b: int) -> None:
        root_a, root_b = self.find(a), self.find(b)
        if root_a != root_b:
            self._parent[max(root_a, root_b)] = min(root_a, root_b)


def _quality(item: ContentItem, index: int) -> tuple[int, int, int]:
    """Which duplicate to keep: best date confidence, then has a snippet, then first seen."""
    return (_DATE_RANK[item.date_confidence], 0 if item.snippet else 1, index)


def find_exact_duplicates(
    items: Sequence[ContentItem],
    known_content_hashes: Collection[str] = (),
    known_url_hashes: Collection[str] = (),
) -> tuple[list[int], list[DroppedDuplicate]]:
    """Split input indexes into (kept, dropped). Duplicates share a content hash or a URL hash
    (transitively); the best-quality member of each set is kept. Items whose hash is already in
    `known_*` (stored earlier) are dropped as `already_stored`."""
    known_content, known_urls = set(known_content_hashes), set(known_url_hashes)
    dropped: list[DroppedDuplicate] = []
    live: list[int] = []
    for index, item in enumerate(items):
        if item.content_hash in known_content or item.url_hash in known_urls:
            dropped.append(
                DroppedDuplicate(index=index, reason=DropReason.already_stored)
            )
        else:
            live.append(index)

    sets = _UnionFind(len(items))
    first_by_content: dict[str, int] = {}
    first_by_url: dict[str, int] = {}
    for index in live:
        item = items[index]
        for table, key in (
            (first_by_content, item.content_hash),
            (first_by_url, item.url_hash),
        ):
            if key in table:
                sets.union(index, table[key])
            else:
                table[key] = index

    members: dict[int, list[int]] = {}
    for index in live:
        members.setdefault(sets.find(index), []).append(index)

    kept: list[int] = []
    for group in members.values():
        winner = min(group, key=lambda i: _quality(items[i], i))
        kept.append(winner)
        for index in group:
            if index == winner:
                continue
            same_text = items[index].content_hash == items[winner].content_hash
            reason = (
                DropReason.duplicate_content_hash
                if same_text
                else DropReason.duplicate_url
            )
            dropped.append(DroppedDuplicate(index=index, reason=reason))
    kept.sort()
    dropped.sort(key=lambda d: d.index)
    return kept, dropped


def assign_dup_groups(items: Sequence[ContentItem]) -> tuple[dict[int, str], int]:
    """dup_group per input index, plus the number of groups with two or more members."""
    groups: dict[int, str] = {}
    by_key: dict[str, str] = {}
    representatives: list[tuple[str, frozenset[str]]] = []
    sizes: dict[str, int] = {}
    for index, item in enumerate(items):
        key = title_key(item.title, item.author)
        tokens = frozenset(key.split())
        group = by_key.get(key) if key else None
        if group is None and len(tokens) >= MIN_FUZZY_TOKENS:
            for rep_group, rep_tokens in representatives:
                if (
                    len(rep_tokens) >= MIN_FUZZY_TOKENS
                    and jaccard(tokens, rep_tokens) >= NEAR_DUPLICATE_THRESHOLD
                ):
                    group = rep_group
                    break
        if group is None:
            group = group_id(key, item.url_hash)
            representatives.append((group, tokens))
            if key:
                by_key[key] = group
        groups[index] = group
        sizes[group] = sizes.get(group, 0) + 1
    return groups, sum(1 for size in sizes.values() if size >= 2)


def dedupe(
    items: Sequence[ContentItem],
    known_content_hashes: Collection[str] = (),
    known_url_hashes: Collection[str] = (),
) -> DedupeResult:
    """Drop exact duplicates, then group near duplicates among what is kept."""
    kept, dropped = find_exact_duplicates(items, known_content_hashes, known_url_hashes)
    kept_items = [items[i] for i in kept]
    groups, multi = assign_dup_groups(kept_items)
    return DedupeResult(
        kept=kept,
        dropped=dropped,
        dup_groups={kept[position]: group for position, group in groups.items()},
        near_duplicate_groups=multi,
    )
