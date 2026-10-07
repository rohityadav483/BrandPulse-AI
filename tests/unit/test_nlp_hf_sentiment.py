"""HFSentimentAnalyzer with a fake classifier. No torch, no transformers, no model, no network."""

import math

import pytest

from app.schemas.domain import Sentiment
from app.services.nlp import model_loader
from app.services.nlp.hf_sentiment import (
    DEFAULT_MODEL_ID,
    DEFAULT_NEUTRAL_MARGIN,
    HFSentimentAnalyzer,
    map_labels,
    to_result,
)
from app.services.nlp.model_loader import ModelUnavailableError
from app.services.nlp.sentiment import SentimentAnalyzer

THREE = ("negative", "neutral", "positive")  # output columns of the default model


class FakeClassifier:
    """Rows follow the keywords in the text; records every batch it is asked to score."""

    def __init__(self, labels=THREE):
        self.labels = tuple(labels)
        self.batches: list[list[str]] = []

    def predict_proba(self, texts):
        self.batches.append(list(texts))
        return [self._row(t) for t in texts]

    def _row(self, text):
        by_class = {"negative": 0.05, "neutral": 0.9, "positive": 0.05}
        if "terrible" in text:
            by_class = {"negative": 0.9, "neutral": 0.07, "positive": 0.03}
        elif "amazing" in text:
            by_class = {"negative": 0.03, "neutral": 0.07, "positive": 0.9}
        elif "mixed" in text:  # top class barely ahead of the runner-up
            by_class = {"negative": 0.40, "neutral": 0.2, "positive": 0.40 + 0.05}
        row = []
        for label in self.labels:
            key = {"label_0": "negative", "label_1": "neutral", "label_2": "positive"}.get(
                label.lower(), label.lower()
            )
            row.append(by_class.get(key, 0.0))
        total = sum(row)
        return [p / total for p in row]


@pytest.fixture(autouse=True)
def _fresh_cache():
    model_loader.clear_classifier_cache()
    yield
    model_loader.clear_classifier_cache()


def make(classifier=None, **options):
    classifier = classifier or FakeClassifier()
    calls = []

    def factory(config):
        calls.append(config)
        return classifier

    analyzer = HFSentimentAnalyzer("org/some-model", classifier_factory=factory, **options)
    return analyzer, classifier, calls


# ---- interface ----


def test_implements_the_sentiment_analyzer_protocol():
    analyzer, _, _ = make()
    assert isinstance(analyzer, SentimentAnalyzer)
    assert analyzer.model_name == "org/some-model"


def test_default_model_is_the_documented_three_class_roberta():
    assert DEFAULT_MODEL_ID == "cardiffnlp/twitter-roberta-base-sentiment-latest"
    assert HFSentimentAnalyzer().model_name == DEFAULT_MODEL_ID


def test_results_are_valid_aligned_with_inputs_and_deterministic():
    analyzer, _, _ = make()
    texts = ["the camera is amazing", "the battery is terrible", "it exists"]
    first = analyzer.analyze(texts)
    assert [r.label for r in first] == [Sentiment.positive, Sentiment.negative, Sentiment.neutral]
    assert first == analyzer.analyze(texts)
    for result in first:
        assert math.isclose(
            result.positive_prob + result.neutral_prob + result.negative_prob, 1.0, abs_tol=1e-9
        )
    assert first[0].score > 0.8 and first[1].score < -0.8


def test_bare_string_is_rejected():
    analyzer, _, _ = make()
    with pytest.raises(TypeError):
        analyzer.analyze("one string")


def test_non_string_entry_is_rejected():
    analyzer, _, _ = make()
    with pytest.raises(TypeError):
        analyzer.analyze(["ok", 3])  # type: ignore[list-item]


# ---- laziness ----


def test_constructing_loads_nothing():
    analyzer, _, calls = make()
    assert calls == [] and not analyzer.is_loaded


def test_empty_input_and_blank_texts_never_load_the_model():
    analyzer, _, calls = make()
    assert analyzer.analyze([]) == []
    results = analyzer.analyze(["", "   ", "\n\t"])
    assert all(r.label is Sentiment.neutral and r.neutral_prob == 1.0 for r in results)
    assert calls == [] and not analyzer.is_loaded


def test_model_loads_once_on_first_real_text_and_is_reused():
    analyzer, classifier, calls = make()
    analyzer.analyze(["the camera is amazing"])
    analyzer.analyze(["the battery is terrible"])
    assert len(calls) == 1 and analyzer.is_loaded
    assert classifier.batches == [["the camera is amazing"], ["the battery is terrible"]]


def test_two_analyzers_with_the_same_config_share_one_loaded_model():
    classifier = FakeClassifier()
    first, _, calls_first = make(classifier)
    second, _, calls_second = make(classifier)
    first.analyze(["the camera is amazing"])
    second.analyze(["the camera is amazing"])
    assert len(calls_first) + len(calls_second) == 1


def test_a_failed_load_is_not_cached_and_can_be_retried():
    attempts = []

    def flaky(config):
        attempts.append(config)
        if len(attempts) == 1:
            raise ModelUnavailableError("offline")
        return FakeClassifier()

    analyzer = HFSentimentAnalyzer("org/flaky", classifier_factory=flaky)
    with pytest.raises(ModelUnavailableError):
        analyzer.analyze(["the camera is amazing"])
    assert not analyzer.is_loaded
    assert analyzer.analyze(["the camera is amazing"])[0].label is Sentiment.positive
    assert len(attempts) == 2


# ---- batching and order ----


def test_batches_by_batch_size_and_keeps_order_with_blanks_in_between():
    analyzer, classifier, _ = make(batch_size=2)
    texts = ["amazing a", "", "terrible b", "amazing c", "  ", "terrible d"]
    results = analyzer.analyze(texts)
    assert [len(batch) for batch in classifier.batches] == [2, 2]
    assert [t for batch in classifier.batches for t in batch] == [
        "amazing a",
        "terrible b",
        "amazing c",
        "terrible d",
    ]
    assert [r.label for r in results] == [
        Sentiment.positive,
        Sentiment.neutral,
        Sentiment.negative,
        Sentiment.positive,
        Sentiment.neutral,
        Sentiment.negative,
    ]


def test_wrong_row_count_from_the_classifier_is_an_error():
    class Short(FakeClassifier):
        def predict_proba(self, texts):
            return super().predict_proba(texts)[:-1]

    analyzer, _, _ = make(Short())
    with pytest.raises(ValueError, match="rows"):
        analyzer.analyze(["amazing a", "terrible b"])


# ---- label mapping ----


@pytest.mark.parametrize(
    ("labels", "expected"),
    [
        (
            ("negative", "neutral", "positive"),
            (Sentiment.negative, Sentiment.neutral, Sentiment.positive),
        ),
        (
            ("positive", "neutral", "negative"),
            (Sentiment.positive, Sentiment.neutral, Sentiment.negative),
        ),
        (
            ("LABEL_0", "LABEL_1", "LABEL_2"),
            (Sentiment.negative, Sentiment.neutral, Sentiment.positive),
        ),
        (("NEGATIVE", "POSITIVE"), (Sentiment.negative, Sentiment.positive)),
        (("Neg", "Neu", "Pos"), (Sentiment.negative, Sentiment.neutral, Sentiment.positive)),
    ],
)
def test_map_labels(labels, expected):
    assert map_labels(labels) == expected


@pytest.mark.parametrize(
    "labels",
    [
        ("negative", "neutral", "joy"),  # unknown label
        ("negative", "negative", "positive"),  # repeated class
        ("negative", "neutral"),  # no positive class
        ("neutral", "positive"),  # no negative class
        (),
    ],
)
def test_map_labels_rejects_models_it_would_mislabel(labels):
    with pytest.raises(ModelUnavailableError):
        map_labels(labels)


def test_model_with_unsupported_labels_fails_on_first_use_not_silently():
    analyzer, _, _ = make(FakeClassifier(("negative", "neutral", "joy")))
    with pytest.raises(ModelUnavailableError):
        analyzer.analyze(["the camera is amazing"])


@pytest.mark.parametrize(
    "labels", [THREE, ("positive", "neutral", "negative"), ("LABEL_0", "LABEL_1", "LABEL_2")]
)
def test_label_order_of_the_model_does_not_change_the_answer(labels):
    analyzer, _, _ = make(FakeClassifier(labels))
    results = analyzer.analyze(["the camera is amazing", "the battery is terrible"])
    assert [r.label for r in results] == [Sentiment.positive, Sentiment.negative]


def test_binary_model_has_zero_neutral_probability_and_margin_gives_neutral():
    analyzer, _, _ = make(FakeClassifier(("NEGATIVE", "POSITIVE")))
    clear, close = analyzer.analyze(["the camera is amazing", "mixed feelings"])
    assert clear.label is Sentiment.positive and clear.neutral_prob == 0.0
    assert close.label is Sentiment.neutral and close.neutral_prob == 0.0


# ---- margin rule ----


def test_low_margin_prediction_becomes_neutral_but_keeps_probabilities():
    analyzer, _, _ = make()
    (result,) = analyzer.analyze(["mixed feelings"])  # positive 0.45 vs negative 0.40
    assert result.label is Sentiment.neutral
    assert result.positive_prob > result.negative_prob  # raw probabilities are not rewritten


def test_margin_is_configurable_and_zero_disables_the_rule():
    analyzer, _, _ = make(neutral_margin=0.0)
    (result,) = analyzer.analyze(["mixed feelings"])
    assert result.label is Sentiment.positive


def test_margin_boundary_is_inclusive():
    classes = (Sentiment.negative, Sentiment.neutral, Sentiment.positive)
    assert to_result([0.25, 0.0, 0.75], classes, 0.5).label is Sentiment.positive
    assert to_result([0.375, 0.0, 0.625], classes, 0.5).label is Sentiment.neutral


def test_to_result_renormalises_slightly_off_probabilities():
    classes = (Sentiment.negative, Sentiment.neutral, Sentiment.positive)
    result = to_result([0.1, 0.1, 0.7], classes, 0.15)  # sums to 0.9
    assert math.isclose(result.positive_prob + result.neutral_prob + result.negative_prob, 1.0)
    assert result.label is Sentiment.positive


@pytest.mark.parametrize(
    "row",
    [[0.2, 0.8], [float("nan"), 0.5, 0.5], [-0.1, 0.6, 0.5], [0.0, 0.0, 0.0], [1e999, 0.1, 0.1]],
)
def test_to_result_rejects_invalid_rows(row):
    with pytest.raises(ValueError):
        to_result(row, (Sentiment.negative, Sentiment.neutral, Sentiment.positive), 0.15)


# ---- configuration ----


def test_config_tag_reflects_settings_that_change_results():
    default, _, _ = make()
    other, _, _ = make(neutral_margin=0.3)
    longer, _, _ = make(max_length=128)
    assert default.config_tag == f"margin-{DEFAULT_NEUTRAL_MARGIN:g}-len256"
    assert len({default.config_tag, other.config_tag, longer.config_tag}) == 3


@pytest.mark.parametrize(
    "options",
    [{"batch_size": 0}, {"max_length": 4}, {"neutral_margin": -0.1}, {"neutral_margin": 1.0}],
)
def test_invalid_options_are_rejected(options):
    with pytest.raises(ValueError):
        HFSentimentAnalyzer("org/m", **options)


@pytest.mark.parametrize("model_id", ["", "   "])
def test_blank_model_id_is_rejected(model_id):
    with pytest.raises(ValueError):
        HFSentimentAnalyzer(model_id)


def test_from_settings_uses_sentiment_model_and_hf_home(make_settings):
    analyzer = HFSentimentAnalyzer.from_settings(
        make_settings(sentiment_model="org/custom", hf_home="/models")
    )
    assert analyzer.model_name == "org/custom"
    assert analyzer._config.cache_dir == "/models"
    assert not analyzer.is_loaded


def test_from_settings_defaults_when_unset(make_settings):
    analyzer = HFSentimentAnalyzer.from_settings(make_settings())
    assert analyzer.model_name == DEFAULT_MODEL_ID
    assert analyzer._config.cache_dir is None
