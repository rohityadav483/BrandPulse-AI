"""Hugging Face sentiment analyzer: implements `SentimentAnalyzer` with a local model.

Default model `cardiffnlp/twitter-roberta-base-sentiment-latest` (3 classes), configurable
through `Settings.sentiment_model` / `hf_home`. Binary models (SST-2 style) work too: their
missing neutral class gets probability 0 and the margin rule supplies neutral.

Lazy: constructing the analyzer loads nothing. The model loads on the first `analyze` call
with at least one non-blank text, through `model_loader.get_classifier`. A
`classifier_factory` can be injected so tests never load a real model.

Rules (docs/ARCHITECTURE.md 5.1): batched CPU inference; probabilities renormalised to sum
to 1; a prediction whose top class beats the runner-up by less than `neutral_margin` becomes
`neutral` (probabilities are kept). Blank text is neutral without inference.
"""

import math
from collections.abc import Sequence

from app.schemas.domain import Sentiment
from app.services.nlp.model_loader import (
    DEFAULT_MAX_LENGTH,
    ClassifierConfig,
    ClassifierFactory,
    ModelUnavailableError,
    SequenceClassifier,
    get_classifier,
    load_sequence_classifier,
)
from app.services.nlp.sentiment import SentimentResult

DEFAULT_MODEL_ID = "cardiffnlp/twitter-roberta-base-sentiment-latest"
DEFAULT_BATCH_SIZE = 16
# Untuned starting value. The Phase 4 eval set must tune it; changing it changes
# `analyzer_version` through `config_tag`, so old results are not reused.
DEFAULT_NEUTRAL_MARGIN = 0.15

_BLANK_RESULT = SentimentResult(Sentiment.neutral, 0.0, 1.0, 0.0)

# Raw label -> sentiment. `LABEL_n` follows the 3-class cardiffnlp convention
# (0 negative, 1 neutral, 2 positive).
_LABELS: dict[str, Sentiment] = {
    "negative": Sentiment.negative,
    "neg": Sentiment.negative,
    "label_0": Sentiment.negative,
    "neutral": Sentiment.neutral,
    "neu": Sentiment.neutral,
    "label_1": Sentiment.neutral,
    "positive": Sentiment.positive,
    "pos": Sentiment.positive,
    "label_2": Sentiment.positive,
}


def map_labels(labels: Sequence[str]) -> tuple[Sentiment, ...]:
    """Map a model's output labels to sentiments, one per output column.

    Raises `ModelUnavailableError` when a label is unknown, repeated, or the model lacks a
    positive or negative class (it would silently mislabel everything).
    """
    mapped: list[Sentiment] = []
    for raw in labels:
        sentiment = _LABELS.get(str(raw).strip().casefold())
        if sentiment is None:
            raise ModelUnavailableError(f"unsupported sentiment label {raw!r} in {list(labels)}")
        mapped.append(sentiment)
    if len(set(mapped)) != len(mapped):
        raise ModelUnavailableError(f"duplicate sentiment classes in labels {list(labels)}")
    if Sentiment.positive not in mapped or Sentiment.negative not in mapped:
        raise ModelUnavailableError(f"model needs a positive and a negative class: {list(labels)}")
    return tuple(mapped)


def to_result(
    row: Sequence[float], classes: Sequence[Sentiment], neutral_margin: float
) -> SentimentResult:
    """Class probabilities of one text -> `SentimentResult` (renormalise, apply margin)."""
    if len(row) != len(classes):
        raise ValueError(f"expected {len(classes)} probabilities, got {len(row)}")
    if any(math.isnan(p) or math.isinf(p) or p < 0 for p in row):
        raise ValueError(f"invalid class probabilities: {list(row)}")
    total = math.fsum(row)
    if total <= 0:
        raise ValueError("class probabilities sum to zero")
    by_class = {Sentiment.positive: 0.0, Sentiment.neutral: 0.0, Sentiment.negative: 0.0}
    for sentiment, probability in zip(classes, row, strict=True):
        by_class[sentiment] = probability / total
    ranked = sorted(by_class.items(), key=lambda item: item[1], reverse=True)
    top_class, top_prob = ranked[0]
    runner_up_prob = ranked[1][1]
    label = top_class if top_prob - runner_up_prob >= neutral_margin else Sentiment.neutral
    return SentimentResult(
        label,
        by_class[Sentiment.positive],
        by_class[Sentiment.neutral],
        by_class[Sentiment.negative],
    )


class HFSentimentAnalyzer:
    """Local transformer sentiment analyzer behind the `SentimentAnalyzer` protocol."""

    def __init__(
        self,
        model_id: str = DEFAULT_MODEL_ID,
        *,
        cache_dir: str | None = None,
        local_files_only: bool = False,
        batch_size: int = DEFAULT_BATCH_SIZE,
        max_length: int = DEFAULT_MAX_LENGTH,
        neutral_margin: float = DEFAULT_NEUTRAL_MARGIN,
        classifier_factory: ClassifierFactory | None = None,
    ) -> None:
        if not model_id or not model_id.strip():
            raise ValueError("model_id must not be blank")
        if batch_size < 1:
            raise ValueError("batch_size must be at least 1")
        if max_length < 8:
            raise ValueError("max_length must be at least 8")
        if not 0.0 <= neutral_margin < 1.0:
            raise ValueError("neutral_margin must be in [0, 1)")
        self.model_name: str = model_id.strip()
        self._config = ClassifierConfig(
            model_id=self.model_name,
            cache_dir=cache_dir or None,
            local_files_only=local_files_only,
            max_length=max_length,
        )
        self._batch_size = batch_size
        self._neutral_margin = neutral_margin
        self._factory: ClassifierFactory = classifier_factory or load_sequence_classifier
        self._classes: tuple[Sentiment, ...] | None = None
        self._classifier: SequenceClassifier | None = None

    @classmethod
    def from_settings(cls, settings: object, **options) -> "HFSentimentAnalyzer":
        """Build from `Settings` (`sentiment_model`, `hf_home`). Still loads nothing."""
        return cls(
            getattr(settings, "sentiment_model", "") or DEFAULT_MODEL_ID,
            cache_dir=getattr(settings, "hf_home", "") or None,
            **options,
        )

    @property
    def config_tag(self) -> str:
        """Settings that change results; part of `analyzer_version`."""
        return f"margin-{self._neutral_margin:g}-len{self._config.max_length}"

    @property
    def is_loaded(self) -> bool:
        return self._classifier is not None

    def _ensure_loaded(self) -> tuple[SequenceClassifier, tuple[Sentiment, ...]]:
        if self._classifier is None or self._classes is None:
            classifier = get_classifier(self._config, factory=self._factory)
            self._classes = map_labels(classifier.labels)
            self._classifier = classifier
        return self._classifier, self._classes

    def analyze(self, texts: Sequence[str]) -> list[SentimentResult]:
        if isinstance(texts, str):
            raise TypeError("texts must be a sequence of strings, not a single string")
        results: list[SentimentResult | None] = [None] * len(texts)
        pending: list[int] = []
        for position, text in enumerate(texts):
            if not isinstance(text, str):
                raise TypeError(f"texts must be strings, got {type(text).__name__}")
            if text.strip():
                pending.append(position)
            else:
                results[position] = _BLANK_RESULT
        if pending:
            classifier, classes = self._ensure_loaded()
            for start in range(0, len(pending), self._batch_size):
                chunk = pending[start : start + self._batch_size]
                rows = classifier.predict_proba([texts[i] for i in chunk])
                if len(rows) != len(chunk):
                    raise ValueError(f"classifier returned {len(rows)} rows for {len(chunk)} texts")
                for position, row in zip(chunk, rows, strict=True):
                    results[position] = to_result(row, classes, self._neutral_margin)
        return [result for result in results if result is not None]
