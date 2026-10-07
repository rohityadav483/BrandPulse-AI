"""dedupe: exact duplicates, near-duplicate grouping, dup_group. Pure, table-driven."""

import hashlib
from datetime import UTC, datetime

import pytest

from app.schemas.domain import ContentPurpose, DateConfidence, SourceType, WindowKind
from app.schemas.processing import ContentItem, DropReason
from app.schemas.serp import SerpEngine
from app.services.processing.dedupe import (
    NEAR_DUPLICATE_THRESHOLD,
    assign_dup_groups,
    dedupe,
    find_exact_duplicates,
    group_id,
    jaccard,
)
from app.services.processing.normalizer import content_hash, title_key, url_hash

NOW = datetime(2026, 8, 10, tzinfo=UTC)


def item(
    title="Galaxy S25 Ultra battery drain after the July update",
    url="https://news.example.test/a",
    snippet="Users report faster battery drain.",
    author="Example Daily",
    confidence=DateConfidence.exact,
) -> ContentItem:
    return ContentItem(
        purpose=ContentPurpose.collection,
        window=WindowKind.current,
        source_type=SourceType.news,
        engine=SerpEngine.google_news,
        url=url,
        url_hash=url_hash(url),
        domain="news.example.test",
        title=title,
        snippet=snippet,
        author=author,
        published_at=None if confidence is DateConfidence.unknown else NOW,
        date_confidence=confidence,
        query="q",
        content_hash=content_hash(title, snippet),
        collected_at=NOW,
    )


# ---------- exact duplicates ----------


def test_unique_items_are_all_kept():
    items = [
        item(
            title=f"Distinct headline number {n} about phones",
            url=f"https://a.test/{n}",
        )
        for n in range(4)
    ]
    kept, dropped = find_exact_duplicates(items)
    assert kept == [0, 1, 2, 3] and dropped == []


def test_same_content_hash_is_an_exact_duplicate():
    a = item(url="https://a.test/1")
    b = item(
        url="https://b.test/2", title=a.title.upper() + "!"
    )  # same normalized text
    assert a.content_hash == b.content_hash
    kept, dropped = find_exact_duplicates([a, b])
    assert kept == [0]
    assert [(d.index, d.reason) for d in dropped] == [
        (1, DropReason.duplicate_content_hash)
    ]


def test_same_canonical_url_is_an_exact_duplicate_even_with_different_snippet():
    a = item(snippet="first snippet", url="https://a.test/page")
    b = item(
        snippet="a different snippet",
        url="https://a.test/page",
        title="Other headline here",
    )
    assert a.content_hash != b.content_hash and a.url_hash == b.url_hash
    kept, dropped = find_exact_duplicates([a, b])
    assert kept == [0] and dropped[0].reason is DropReason.duplicate_url


def test_duplicates_are_transitive_across_hash_kinds():
    a = item(
        title="First headline about phones today", url="https://a.test/1", snippet="s1"
    )
    b = item(
        title="First headline about phones today", url="https://a.test/2", snippet="s1"
    )
    c = item(title="Unrelated words entirely", url="https://a.test/2", snippet="other")
    kept, dropped = find_exact_duplicates([a, b, c])
    assert len(kept) == 1 and len(dropped) == 2


def test_best_quality_duplicate_wins_over_first_seen():
    vague = item(
        url="https://a.test/1", confidence=DateConfidence.unknown, snippet="same"
    )
    dated = item(
        url="https://a.test/1", confidence=DateConfidence.exact, snippet="same"
    )
    kept, dropped = find_exact_duplicates([vague, dated])
    assert kept == [1] and dropped[0].index == 0


def test_a_snippet_beats_no_snippet_at_equal_date_quality():
    bare = item(url="https://a.test/1", snippet=None)
    full = item(url="https://a.test/1", snippet="has text")
    kept, _ = find_exact_duplicates([bare, full])
    assert kept == [1]


def test_first_seen_wins_a_full_tie_and_order_is_preserved():
    items = [
        item(title="Zebra headline about phones today", url="https://a.test/z"),
        item(title="Alpha headline about phones today", url="https://a.test/a"),
        item(title="Zebra headline about phones today", url="https://a.test/z"),
    ]
    kept, dropped = find_exact_duplicates(items)
    assert kept == [0, 1] and [d.index for d in dropped] == [2]


def test_items_already_stored_are_dropped_as_already_stored():
    a, b = (
        item(url="https://a.test/1"),
        item(title="Brand new headline for today", url="https://a.test/2"),
    )
    kept, dropped = find_exact_duplicates([a, b], known_content_hashes={a.content_hash})
    assert kept == [1] and dropped[0].reason is DropReason.already_stored
    kept, dropped = find_exact_duplicates([a, b], known_url_hashes={b.url_hash})
    assert kept == [0] and dropped[0].reason is DropReason.already_stored


def test_empty_input():
    assert find_exact_duplicates([]) == ([], [])
    result = dedupe([])
    assert (
        result.kept == [] and result.dropped == [] and result.near_duplicate_groups == 0
    )


# ---------- near duplicates / dup_group ----------


def test_identical_normalized_titles_share_a_group_and_the_group_is_the_title_hash():
    a = item(
        title="Galaxy S25 Ultra: battery drain!", url="https://a.test/1", snippet="x"
    )
    b = item(
        title="galaxy s25 ultra battery drain", url="https://b.test/2", snippet="y"
    )
    groups, multi = assign_dup_groups([a, b])
    assert groups[0] == groups[1] and multi == 1
    assert groups[0] == hashlib.sha256(b"galaxy s25 ultra battery drain").hexdigest()


def test_syndicated_outlet_suffix_is_ignored_when_it_matches_the_author():
    a = item(
        title="Samsung confirms charging slowdown on S25 - Example Wire",
        author="Example Wire",
        url="https://a.test/1",
    )
    b = item(
        title="Samsung confirms charging slowdown on S25",
        author="Other Outlet",
        url="https://b.test/2",
        snippet="different",
    )
    groups, multi = assign_dup_groups([a, b])
    assert groups[0] == groups[1] and multi == 1


def test_a_real_subtitle_is_not_stripped():
    a = item(
        title="Samsung confirms charging slowdown on S25 - what owners should do",
        author="X",
        url="https://a.test/1",
    )
    b = item(
        title="Samsung confirms charging slowdown on S25",
        author="Y",
        url="https://b.test/2",
        snippet="different",
    )
    groups, _ = assign_dup_groups([a, b])
    assert groups[0] != groups[1]


def test_lightly_edited_headlines_group_by_token_overlap():
    a = item(
        title="Galaxy S25 Ultra owners report severe battery drain after update",
        url="https://a.test/1",
    )
    b = item(
        title="Galaxy S25 Ultra owners report severe battery drain after update again",
        url="https://b.test/2",
        snippet="other",
    )
    ta, tb = (frozenset(title_key(i.title).split()) for i in (a, b))
    assert jaccard(ta, tb) >= NEAR_DUPLICATE_THRESHOLD
    groups, multi = assign_dup_groups([a, b])
    assert groups[0] == groups[1] and multi == 1


def test_loosely_related_headlines_stay_separate():
    a = item(
        title="Galaxy S25 Ultra owners report battery drain after update",
        url="https://a.test/1",
    )
    b = item(
        title="Galaxy S25 Ultra camera update improves low light photos",
        url="https://b.test/2",
        snippet="other",
    )
    groups, multi = assign_dup_groups([a, b])
    assert groups[0] != groups[1] and multi == 0


def test_short_titles_only_group_on_exact_match():
    a = item(title="S25 battery drain", url="https://a.test/1")
    b = item(
        title="S25 battery drain now", url="https://b.test/2", snippet="other"
    )  # jaccard .75
    c = item(title="S25 battery drain", url="https://c.test/3", snippet="third")
    groups, multi = assign_dup_groups([a, b, c])
    assert groups[0] == groups[2] and groups[0] != groups[1] and multi == 1


def test_groups_do_not_chain_through_intermediate_titles():
    base = "alpha beta gamma delta epsilon zeta eta theta iota kappa"
    a = item(title=base, url="https://a.test/1")
    b = item(
        title=base + " lambda", url="https://b.test/2", snippet="b"
    )  # 10/11 with a
    c = item(
        title=base + " lambda mu nu", url="https://c.test/3", snippet="c"
    )  # 10/13 with a
    assert (
        jaccard(
            frozenset(title_key(b.title).split()), frozenset(title_key(c.title).split())
        )
        >= 0.8
    )
    groups, _ = assign_dup_groups([a, b, c])
    assert groups[0] == groups[1]  # b joins a
    assert groups[2] != groups[0]  # c is compared with a (not b) and stays apart


def test_punctuation_only_titles_never_share_a_group():
    a = item(title="!!!", url="https://a.test/1", snippet="one")
    b = item(title="???", url="https://b.test/2", snippet="two")
    groups, multi = assign_dup_groups([a, b])
    assert groups[0] != groups[1] and multi == 0
    assert groups[0] == group_id("", a.url_hash)


def test_group_ids_are_deterministic_sha256_hex():
    items = [
        item(url="https://a.test/1"),
        item(title="Other headline entirely different", url="https://a.test/2"),
    ]
    first, _ = assign_dup_groups(items)
    second, _ = assign_dup_groups(items)
    assert first == second
    assert all(len(g) == 64 for g in first.values())


def test_jaccard_edges():
    assert jaccard(frozenset(), frozenset({"a"})) == 0.0
    assert jaccard(frozenset({"a", "b"}), frozenset({"a", "b"})) == 1.0
    assert jaccard(frozenset({"a", "b"}), frozenset({"b", "c"})) == pytest.approx(1 / 3)


# ---------- dedupe(): both steps together ----------


def test_dedupe_drops_exact_then_groups_near_among_the_kept():
    a = item(
        title="Galaxy S25 Ultra owners report severe battery drain after update",
        url="https://a.test/1",
    )
    a_again = item(title=a.title, url="https://a.test/1")  # exact duplicate of a
    b = item(
        title=a.title + " again", url="https://b.test/2", snippet="other"
    )  # near duplicate
    c = item(
        title="Samsung unveils a new foldable phone",
        url="https://c.test/3",
        snippet="c",
    )
    result = dedupe([a, a_again, b, c])
    assert result.kept == [0, 2, 3]
    assert [(d.index, d.reason) for d in result.dropped] == [
        (1, DropReason.duplicate_content_hash)
    ]
    assert result.dup_groups[0] == result.dup_groups[2] != result.dup_groups[3]
    assert result.near_duplicate_groups == 1
    assert set(result.dup_groups) == set(result.kept)
