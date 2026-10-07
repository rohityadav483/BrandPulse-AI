"""`SentimentAnalyzer` interface and a deterministic stub for tests. Pure, stdlib only.

Everything that needs sentiment depends on `SentimentAnalyzer`, never on a concrete model, so
unit tests run with `StubSentimentAnalyzer` and never import torch or load a model
(AGENTS.md rule 5). The Hugging Face implementation (batched, CPU, low-margin -> neutral)
is a later step and will implement the same protocol.

`SentimentResult` carries the three class probabilities; the fields stored in
`content_analysis` / `item_aspects` derive from them: `label`, `score` (-1..1, positive minus
negative probability) and `negative_prob`.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from app.schemas.domain import Sentiment
from app.services.nlp.textnorm import normalize_text

_PROB_TOLERANCE = 1e-6


@dataclass(frozen=True, slots=True)
class SentimentResult:
    label: Sentiment
    positive_prob: float
    neutral_prob: float
    negative_prob: float

    def __post_init__(self) -> None:
        probs = (self.positive_prob, self.neutral_prob, self.negative_prob)
        if any(not (0.0 <= p <= 1.0) or math.isnan(p) for p in probs):
            raise ValueError(f"probabilities must be within [0, 1], got {probs}")
        if abs(sum(probs) - 1.0) > _PROB_TOLERANCE:
            raise ValueError(f"probabilities must sum to 1, got {probs}")

    @property
    def score(self) -> float:
        """-1.0 (certainly negative) to 1.0 (certainly positive)."""
        return self.positive_prob - self.negative_prob


@runtime_checkable
class SentimentAnalyzer(Protocol):
    """Turns texts into sentiment results.

    `model_name` identifies the model (stored in `content_analysis.model`, part of
    `analyzer_version`). `analyze` returns exactly one result per input text, in the same order,
    and returns `[]` for no texts. It must be deterministic for a given model.
    """

    model_name: str

    def analyze(self, texts: Sequence[str]) -> list[SentimentResult]: ...


STUB_MODEL_NAME = "stub-lexicon-v1"

_POSITIVE = frozenset(
    {
        "amazing",
        "awesome",
        "best",
        "beautiful",
        "bright",
        "brilliant",
        "excellent",
        "fantastic",
        "fast",
        "good",
        "gorgeous",
        "great",
        "happy",
        "impressive",
        "love",
        "loved",
        "nice",
        "perfect",
        "recommend",
        "reliable",
        "sharp",
        "smooth",
        "solid",
        "stunning",
        "superb",
        "worth",
    }
)
_NEGATIVE = frozenset(
    {
        "annoying",
        "awful",
        "bad",
        "broken",
        "bug",
        "buggy",
        "disappointed",
        "disappointing",
        "drain",
        "drains",
        "draining",
        "expensive",
        "garbage",
        "hate",
        "hated",
        "horrible",
        "issue",
        "issues",
        "laggy",
        "mediocre",
        "overheating",
        "overpriced",
        "poor",
        "problem",
        "problems",
        "regret",
        "slow",
        "terrible",
        "unreliable",
        "useless",
        "worst",
    }
)
# "t" comes from "n't" ("isn't" -> "isn t") after normalisation.
_NEGATORS = frozenset({"not", "no", "never", "hardly", "without", "t"})
_NEGATION_WINDOW = 2


def _dominant_probs(positive: int, negative: int) -> tuple[float, float, float]:
    """(positive, neutral, negative) probabilities from hit counts. Always consistent with the
    label rule: more positive hits -> positive is the largest probability, and so on."""
    total = positive + negative
    if total == 0:
        return 0.0, 1.0, 0.0
    if positive == negative:
        return 0.25, 0.5, 0.25
    major, minor = max(positive, negative), min(positive, negative)
    dominant = 0.5 + 0.4 * (major - minor) / (total + 1)
    remaining = 1.0 - dominant
    opposing = remaining * minor / total
    neutral = remaining - opposing
    if positive > negative:
        return dominant, neutral, opposing
    return opposing, neutral, dominant


class StubSentimentAnalyzer:
    """Keyword-count analyzer for tests. No model, no I/O, fully deterministic.

    Counts positive and negative words in the normalised text; a negator (`not`, `never`,
    `isn't`, ...) within the two preceding words flips that word (`not bad` is positive).
    More positive than negative -> positive, more negative -> negative, otherwise neutral.
    It is a test double, not a quality baseline.
    """

    model_name: str = STUB_MODEL_NAME

    def analyze(self, texts: Sequence[str]) -> list[SentimentResult]:
        if isinstance(texts, str):
            raise TypeError("texts must be a sequence of strings, not a single string")
        return [self._analyze_one(text) for text in texts]

    @staticmethod
    def _analyze_one(text: str) -> SentimentResult:
        words = normalize_text(text).split()
        positive = negative = 0
        for position, word in enumerate(words):
            if word in _POSITIVE:
                polarity = 1
            elif word in _NEGATIVE:
                polarity = -1
            else:
                continue
            window = words[max(0, position - _NEGATION_WINDOW) : position]
            if any(previous in _NEGATORS for previous in window):
                polarity = -polarity
            if polarity > 0:
                positive += 1
            else:
                negative += 1
        pos_prob, neu_prob, neg_prob = _dominant_probs(positive, negative)
        if positive > negative:
            label = Sentiment.positive
        elif negative > positive:
            label = Sentiment.negative
        else:
            label = Sentiment.neutral
        return SentimentResult(label, pos_prob, neu_prob, neg_prob)
