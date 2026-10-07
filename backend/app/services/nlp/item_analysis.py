"""Turn items into the rows `content_analysis` / `item_aspects` store (docs/ARCHITECTURE.md 5.1).

Per item: relevance rule first (an item that is not about the brand gets a neutral row and no
inference); then overall sentiment on `title + snippet`, clause split, aspect lexicon match and
one sentiment per aspect clause. All model work for a call goes through one
`SentimentAnalyzer.analyze` call, so a real model batches across items. Pure: no DB, no I/O
besides the analyzer.

Keywords (`keywords.extract_keywords`, per-text frequency, brand terms excluded) and topics
(`topics.derive_topics`: aspect names plus top keywords) are deterministic rules computed from
the item's own text, so they do not depend on the batch and stay reusable by `analyzer_version`.
Irrelevant items get none.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from app.config.taxonomy import DEFAULT_CATEGORY
from app.schemas.domain import Category, Sentiment
from app.schemas.nlp import AspectSentiment, ItemAnalysis
from app.services.nlp.analyzer_version import analyzer_version_for
from app.services.nlp.aspects import AspectClause, detect_aspects_in_text
from app.services.nlp.keywords import extract_keywords
from app.services.nlp.relevance import BrandProfile, RelevanceResult, detect_relevance
from app.services.nlp.sentiment import SentimentAnalyzer, SentimentResult
from app.services.nlp.topics import derive_topics

_TERMINATORS = (".", "!", "?", ";", "…")


@dataclass(frozen=True, slots=True)
class ItemText:
    """The analyzable text of one item: its title and snippet."""

    title: str
    snippet: str | None = None


def full_text(item: ItemText) -> str:
    """Title and snippet analyzed together; a title without end punctuation gets a full stop,
    so the clause splitter does not run the two into one sentence."""
    title = (item.title or "").strip()
    snippet = (item.snippet or "").strip()
    if not snippet:
        return title
    if not title:
        return snippet
    return f"{title} {snippet}" if title.endswith(_TERMINATORS) else f"{title}. {snippet}"


def _aspect_row(found: AspectClause, result: SentimentResult) -> AspectSentiment:
    return AspectSentiment(
        aspect=found.aspect,
        clause=found.clause.text,
        sentiment=result.label,
        negative_prob=result.negative_prob,
        score=result.score,
    )


def analyze_items(
    items: Sequence[ItemText],
    profile: BrandProfile,
    analyzer: SentimentAnalyzer,
    category: Category | str = DEFAULT_CATEGORY,
) -> list[ItemAnalysis]:
    """One `ItemAnalysis` per item, same order. Calls `analyzer.analyze` at most once."""
    version = analyzer_version_for(analyzer, category)
    relevance: list[RelevanceResult] = [
        detect_relevance(profile, item.title, item.snippet) for item in items
    ]
    texts: list[str] = []  # everything the model must score, in one batch
    overall_slot: dict[int, int] = {}
    aspect_slots: dict[int, list[tuple[AspectClause, int]]] = {}
    item_text: dict[int, str] = {}
    for position, (item, found_relevance) in enumerate(zip(items, relevance, strict=True)):
        if not found_relevance.is_about_brand:
            continue
        text = full_text(item)
        item_text[position] = text
        overall_slot[position] = len(texts)
        texts.append(text)
        slots: list[tuple[AspectClause, int]] = []
        for found in detect_aspects_in_text(text, category):
            slots.append((found, len(texts)))
            texts.append(found.clause.text)
        aspect_slots[position] = slots

    results = analyzer.analyze(texts) if texts else []
    if len(results) != len(texts):
        raise ValueError(f"analyzer returned {len(results)} results for {len(texts)} texts")

    analyses: list[ItemAnalysis] = []
    for position, found_relevance in enumerate(relevance):
        if not found_relevance.is_about_brand:
            analyses.append(
                ItemAnalysis(
                    sentiment=Sentiment.neutral,
                    sentiment_score=0.0,
                    negative_prob=0.0,
                    is_about_brand=False,
                    model=analyzer.model_name,
                    analyzer_version=version,
                )
            )
            continue
        overall = results[overall_slot[position]]
        aspect_rows = tuple(
            _aspect_row(found, results[slot]) for found, slot in aspect_slots[position]
        )
        keywords = extract_keywords(item_text[position], exclude_terms=profile.terms)
        covered = [term for found, _ in aspect_slots[position] for term in found.matched_terms]
        topics = derive_topics([row.aspect for row in aspect_rows], keywords, covered_terms=covered)
        analyses.append(
            ItemAnalysis(
                sentiment=overall.label,
                sentiment_score=overall.score,
                negative_prob=overall.negative_prob,
                is_about_brand=True,
                matched_terms=found_relevance.matched_terms,
                topics=topics,
                keywords=keywords,
                model=analyzer.model_name,
                analyzer_version=version,
                aspects=aspect_rows,
            )
        )
    return analyses
