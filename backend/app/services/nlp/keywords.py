"""Deterministic keyword extraction for one text. Pure, stdlib only.

Rules (`KEYWORD_RULES_VERSION`): normalise with `textnorm.normalize_text`, split into words,
drop stopwords, words shorter than 3 characters, digit-only words and any word that belongs to
an excluded term (the brand and product names), then rank the remaining words by how often
they occur, then by first position, then alphabetically. The result depends on this one text
only, never on other items in the batch. That is deliberate: results are reused by
`(content_hash, analyzer_version)` (docs/ARCHITECTURE.md 5.1), so the same text must always
give the same keywords. A corpus-level TF-IDF would break that reuse and is not implemented.

Keywords are single words in their normalised (casefolded) form; no stemming, no phrases.
Change a rule or the stopword list -> bump `KEYWORD_RULES_VERSION` (part of `analyzer_version`).
"""

from collections.abc import Iterable

from app.services.nlp.textnorm import normalize_text

KEYWORD_RULES_VERSION = "keywords-1"

DEFAULT_MAX_KEYWORDS = 5
MIN_WORD_LENGTH = 3
MAX_WORD_LENGTH = 40

# Function words plus the filler that dominates short review/news snippets. Contraction
# fragments (`don t` -> `don`, `t`) are covered because `normalize_text` splits on apostrophes.
STOPWORDS: frozenset[str] = frozenset(
    [
        "a",
        "about",
        "above",
        "after",
        "again",
        "against",
        "all",
        "also",
        "am",
        "an",
        "and",
        "any",
        "are",
        "aren",
        "as",
        "at",
        "be",
        "because",
        "been",
        "before",
        "being",
        "below",
        "between",
        "both",
        "but",
        "by",
        "can",
        "cannot",
        "could",
        "couldn",
        "did",
        "didn",
        "do",
        "does",
        "doesn",
        "doing",
        "don",
        "down",
        "during",
        "each",
        "few",
        "for",
        "from",
        "further",
        "had",
        "hadn",
        "has",
        "hasn",
        "have",
        "haven",
        "having",
        "he",
        "her",
        "here",
        "hers",
        "him",
        "his",
        "how",
        "i",
        "if",
        "in",
        "into",
        "is",
        "isn",
        "it",
        "its",
        "itself",
        "just",
        "let",
        "ll",
        "me",
        "more",
        "most",
        "mustn",
        "my",
        "myself",
        "no",
        "nor",
        "not",
        "now",
        "of",
        "off",
        "on",
        "once",
        "only",
        "or",
        "other",
        "our",
        "ours",
        "out",
        "over",
        "own",
        "re",
        "same",
        "shan",
        "she",
        "should",
        "shouldn",
        "so",
        "some",
        "such",
        "than",
        "that",
        "the",
        "their",
        "theirs",
        "them",
        "then",
        "there",
        "these",
        "they",
        "this",
        "those",
        "through",
        "to",
        "too",
        "under",
        "until",
        "up",
        "ve",
        "very",
        "was",
        "wasn",
        "we",
        "were",
        "weren",
        "what",
        "when",
        "where",
        "which",
        "while",
        "who",
        "whom",
        "why",
        "will",
        "with",
        "won",
        "would",
        "wouldn",
        "you",
        "your",
        "yours",
        "yourself",
        "get",
        "gets",
        "got",
        "getting",
        "make",
        "makes",
        "made",
        "one",
        "two",
        "new",
        "really",
        "still",
        "even",
        "much",
        "many",
        "lot",
        "lots",
        "like",
        "likes",
        "thing",
        "things",
        "way",
        "ever",
        "never",
        "always",
        "since",
        "though",
        "yet",
        "however",
        "say",
        "says",
        "said",
        "report",
        "reports",
        "reported",
        "via",
        "per",
        "etc",
    ]
)


def _words(text: str | None) -> list[str]:
    return normalize_text(text).split()


def extract_keywords(
    text: str | None,
    *,
    exclude_terms: Iterable[str] = (),
    max_keywords: int = DEFAULT_MAX_KEYWORDS,
) -> tuple[str, ...]:
    """Up to `max_keywords` keywords of `text`, best first. Empty for blank or wordless text.

    `exclude_terms` are brand/product names (or any phrase); every word inside them is skipped,
    so `Samsung Galaxy S25 Ultra` removes `samsung`, `galaxy`, `s25` and `ultra`.
    """
    if isinstance(exclude_terms, str):
        raise TypeError(
            "exclude_terms must be a sequence of strings, not a single string"
        )
    if max_keywords < 0:
        raise ValueError("max_keywords must not be negative")
    if max_keywords == 0:
        return ()
    excluded = {word for term in exclude_terms for word in _words(term)}
    counts: dict[str, int] = {}
    first_seen: dict[str, int] = {}
    for position, word in enumerate(_words(text)):
        if (
            len(word) < MIN_WORD_LENGTH
            or len(word) > MAX_WORD_LENGTH
            or word.isdigit()
            or word in STOPWORDS
            or word in excluded
        ):
            continue
        counts[word] = counts.get(word, 0) + 1
        first_seen.setdefault(word, position)
    ranked = sorted(counts, key=lambda word: (-counts[word], first_seen[word], word))
    return tuple(ranked[:max_keywords])
