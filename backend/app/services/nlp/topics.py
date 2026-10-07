"""Deterministic topics of one item: its aspects plus its top keywords. Pure, stdlib only.

docs/ARCHITECTURE.md 5.1: "topics = aspects plus top keywords". Aspect names come first, in
the order given (`item_analysis` passes them in the order the aspects occur in the text), then
up to `max_keyword_topics` keywords that are not already covered (an aspect name or a term that
matched an aspect, so `battery` is not listed twice). No duplicates. Depends only on its
arguments, so reuse by `(content_hash, analyzer_version)` stays valid. Change a rule -> bump
`TOPIC_RULES_VERSION` (part of `analyzer_version`).
"""

from collections.abc import Iterable, Sequence

from app.services.nlp.textnorm import normalize_text

TOPIC_RULES_VERSION = "topics-1"

DEFAULT_MAX_KEYWORD_TOPICS = 3


def derive_topics(
    aspect_names: Sequence[str],
    keywords: Sequence[str],
    *,
    covered_terms: Iterable[str] = (),
    max_keyword_topics: int = DEFAULT_MAX_KEYWORD_TOPICS,
) -> tuple[str, ...]:
    """Aspect names (deduplicated, given order) followed by up to `max_keyword_topics`
    keywords that are not covered by an aspect name or a `covered_terms` entry."""
    if isinstance(aspect_names, str) or isinstance(keywords, str):
        raise TypeError("aspect_names and keywords must be sequences of strings")
    if isinstance(covered_terms, str):
        raise TypeError("covered_terms must be a sequence of strings, not a single string")
    if max_keyword_topics < 0:
        raise ValueError("max_keyword_topics must not be negative")
    topics: list[str] = []
    for name in aspect_names:
        if name and name not in topics:
            topics.append(name)
    covered = {normalize_text(name) for name in topics}
    for term in covered_terms:
        covered.update(normalize_text(term).split())
        covered.add(normalize_text(term))
    added = 0
    for keyword in keywords:
        if added >= max_keyword_topics:
            break
        key = normalize_text(keyword)
        if not key or key in covered or keyword in topics:
            continue
        topics.append(keyword)
        covered.add(key)
        added += 1
    return tuple(topics)
