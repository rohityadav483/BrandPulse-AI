"""nlp/sentiment: SentimentAnalyzer interface and the deterministic stub."""

import math

import pytest

from app.schemas.domain import Sentiment
from app.services.nlp.sentiment import (
    STUB_MODEL_NAME,
    SentimentAnalyzer,
    SentimentResult,
    StubSentimentAnalyzer,
)

STUB = StubSentimentAnalyzer()


def one(text):
    return STUB.analyze([text])[0]


# --- SentimentResult ------------------------------------------------------------------------


def test_result_score_is_positive_minus_negative():
    result = SentimentResult(Sentiment.positive, 0.7, 0.2, 0.1)
    assert result.score == pytest.approx(0.6)
    assert SentimentResult(Sentiment.negative, 0.0, 0.3, 0.7).score == pytest.approx(-0.7)


@pytest.mark.parametrize(
    "probs",
    [(0.5, 0.5, 0.5), (0.2, 0.2, 0.2), (-0.1, 0.6, 0.5), (1.2, 0.0, -0.2), (math.nan, 0.5, 0.5)],
)
def test_result_rejects_invalid_probabilities(probs):
    with pytest.raises(ValueError):
        SentimentResult(Sentiment.neutral, *probs)


def test_result_is_immutable():
    result = SentimentResult(Sentiment.neutral, 0.0, 1.0, 0.0)
    with pytest.raises(AttributeError):
        result.label = Sentiment.positive  # type: ignore[misc]


# --- interface ------------------------------------------------------------------------------


def test_stub_satisfies_the_interface():
    assert isinstance(STUB, SentimentAnalyzer)
    assert STUB.model_name == STUB_MODEL_NAME


def test_other_implementations_can_satisfy_the_interface():
    class Constant:
        model_name = "constant"

        def analyze(self, texts):
            return [SentimentResult(Sentiment.neutral, 0.0, 1.0, 0.0) for _ in texts]

    assert isinstance(Constant(), SentimentAnalyzer)


def test_objects_without_the_methods_do_not_satisfy_the_interface():
    class Wrong:
        model_name = "wrong"

    assert not isinstance(Wrong(), SentimentAnalyzer)
    assert not isinstance(object(), SentimentAnalyzer)


# --- stub behaviour -------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text,label",
    [
        ("The camera is amazing", Sentiment.positive),
        ("battery life is terrible", Sentiment.negative),
        ("Excellent screen, great speakers", Sentiment.positive),
        ("Awful lag and horrible battery", Sentiment.negative),
        ("The phone arrived on Tuesday", Sentiment.neutral),
        ("It is good but also bad", Sentiment.neutral),
        ("GREAT", Sentiment.positive),
        ("TERRIBLE!!!", Sentiment.negative),
    ],
)
def test_stub_labels(text, label):
    assert one(text).label is label


@pytest.mark.parametrize(
    "text,label",
    [
        ("not bad", Sentiment.positive),
        ("it is not good", Sentiment.negative),
        ("this isn't great", Sentiment.negative),
        ("never terrible", Sentiment.positive),
        ("no problems at all", Sentiment.positive),
    ],
)
def test_stub_negation_flips_a_nearby_word(text, label):
    assert one(text).label is label


def test_stub_negation_only_reaches_two_words_back():
    assert one("not at all bad").label is Sentiment.negative


@pytest.mark.parametrize("text", ["", "   ", "...", "12345"])
def test_stub_empty_or_wordless_text_is_neutral(text):
    result = one(text)
    assert result.label is Sentiment.neutral
    assert (result.positive_prob, result.neutral_prob, result.negative_prob) == (0.0, 1.0, 0.0)
    assert result.score == 0.0


def test_stub_probabilities_agree_with_the_label():
    texts = [
        "great",
        "great great good bad",
        "great good",
        "terrible",
        "terrible awful great",
        "terrible awful horrible",
        "amazing but terrible",
        "nothing special",
        "",
    ]
    for text in texts:
        result = one(text)
        probs = {
            Sentiment.positive: result.positive_prob,
            Sentiment.neutral: result.neutral_prob,
            Sentiment.negative: result.negative_prob,
        }
        assert max(probs, key=probs.get) is result.label, text
        assert sum(probs.values()) == pytest.approx(1.0)


def test_stub_more_evidence_means_more_confidence():
    assert one("great good excellent").positive_prob > one("great").positive_prob
    assert one("terrible awful horrible").negative_prob > one("terrible").negative_prob


def test_stub_score_sign_follows_label():
    assert one("amazing").score > 0
    assert one("terrible").score < 0
    assert one("amazing but terrible").score == 0


def test_stub_returns_one_result_per_text_in_order():
    results = STUB.analyze(["great", "terrible", "ok", ""])
    assert [r.label for r in results] == [
        Sentiment.positive,
        Sentiment.negative,
        Sentiment.neutral,
        Sentiment.neutral,
    ]


def test_stub_no_texts_gives_empty_list():
    assert STUB.analyze([]) == []


def test_stub_is_deterministic_and_stateless():
    texts = ["The camera is amazing", "battery life is terrible"]
    first = STUB.analyze(texts)
    assert first == STUB.analyze(texts)
    assert first == StubSentimentAnalyzer().analyze(texts)
    assert STUB.analyze(list(reversed(texts))) == list(reversed(first))


def test_stub_accepts_tuples():
    assert [r.label for r in STUB.analyze(("great", "bad"))] == [
        Sentiment.positive,
        Sentiment.negative,
    ]


def test_stub_rejects_a_bare_string():
    with pytest.raises(TypeError):
        STUB.analyze("great")  # type: ignore[arg-type]
