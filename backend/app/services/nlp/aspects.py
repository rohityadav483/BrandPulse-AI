"""Lexicon-based aspect detection, mapped to the clause that mentions each aspect.

Pure, stdlib only. Lexicons live in `app.config.taxonomy`. Input is the output of
`clauses.split_clauses`; output has at most one entry per aspect, because
`item_aspects` is keyed `(content_id, aspect)` (docs/DATABASE.md 5.7). When several clauses
mention the same aspect, the clause with the most distinct matched terms wins, ties go to the
earliest clause. One clause can carry several aspects.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from functools import lru_cache

from app.config.taxonomy import DEFAULT_CATEGORY, Lexicon, get_lexicon
from app.schemas.domain import Category
from app.services.nlp.clauses import Clause, split_clauses
from app.services.nlp.textnorm import normalize_text


@dataclass(frozen=True, slots=True)
class AspectClause:
    aspect: str
    clause: Clause
    matched_terms: tuple[str, ...]  # lexicon terms (normalised form) found in the clause


@lru_cache(maxsize=None)
def _compiled(category_key: str) -> tuple[tuple[str, tuple[tuple[str, re.Pattern[str]], ...]], ...]:
    lexicon = get_lexicon(category_key)
    compiled = []
    for aspect, terms in lexicon.items():
        patterns = []
        for term in terms:
            normalized = normalize_text(term)
            if not normalized:
                continue
            body = r"\s+".join(re.escape(word) for word in normalized.split())
            patterns.append((normalized, re.compile(rf"(?<!\w){body}(?:e?s)?(?!\w)")))
        compiled.append((aspect, tuple(patterns)))
    return tuple(compiled)


def _category_key(category: Category | str) -> str:
    return category.value if isinstance(category, Category) else category


def terms_in_text(
    text: str, category: Category | str = DEFAULT_CATEGORY
) -> dict[str, tuple[str, ...]]:
    """Aspects mentioned in one piece of text, with the lexicon terms that matched, in lexicon
    order. Aspects with no match are absent."""
    normalized = normalize_text(text)
    found: dict[str, tuple[str, ...]] = {}
    if not normalized:
        return found
    for aspect, patterns in _compiled(_category_key(category)):
        hits = tuple(term for term, pattern in patterns if pattern.search(normalized))
        if hits:
            found[aspect] = hits
    return found


def detect_aspects(
    clauses: Sequence[Clause], category: Category | str = DEFAULT_CATEGORY
) -> list[AspectClause]:
    """One `AspectClause` per aspect found, ordered by clause position, then lexicon order."""
    best: dict[str, AspectClause] = {}
    for clause in clauses:
        for aspect, hits in terms_in_text(clause.text, category).items():
            current = best.get(aspect)
            if current is None or len(hits) > len(current.matched_terms):
                best[aspect] = AspectClause(aspect, clause, hits)
    order = {aspect: position for position, aspect in enumerate(get_lexicon(category))}
    return sorted(best.values(), key=lambda found: (found.clause.index, order[found.aspect]))


def detect_aspects_in_text(
    text: str | None, category: Category | str = DEFAULT_CATEGORY
) -> list[AspectClause]:
    """Convenience: split into clauses, then detect aspects."""
    return detect_aspects(split_clauses(text), category)


def aspect_names(category: Category | str = DEFAULT_CATEGORY) -> tuple[str, ...]:
    """Aspect names of a preset, in lexicon order."""
    lexicon: Lexicon = get_lexicon(category)
    return tuple(lexicon)
