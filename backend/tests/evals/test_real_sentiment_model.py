"""Real local model smoke test. Marker `model`: excluded from default runs (pytest.ini addopts).

Run on a machine with torch + transformers installed and the model downloaded (or network
access to the Hugging Face hub):

    pytest -m model tests/evals/test_real_sentiment_model.py

Not run in CI. Not run in the Phase 4.2 or 4.3 passes either (no torch, no model files; the
Hugging Face hub was unreachable from the sandbox). Before trusting the margin, also run
`python scripts/run_eval.py --analyzer hf --sweep` on the same machine.
"""

import pytest

from app.schemas.domain import Sentiment
from app.services.nlp.hf_sentiment import HFSentimentAnalyzer
from app.services.nlp.item_analysis import ItemText, analyze_items
from app.services.nlp.relevance import BrandProfile

pytestmark = pytest.mark.model


@pytest.fixture(scope="module")
def analyzer():
    pytest.importorskip("torch")
    pytest.importorskip("transformers")
    return HFSentimentAnalyzer.from_settings(_settings())


def _settings():
    from app.config.settings import Settings

    return Settings(_env_file=None)


def test_clearly_positive_and_negative_texts(analyzer):
    positive, negative = analyzer.analyze(
        [
            "I love this phone, the screen is gorgeous",
            "This is awful, it keeps crashing",
        ]
    )
    assert positive.label is Sentiment.positive and positive.score > 0.5
    assert negative.label is Sentiment.negative and negative.score < -0.5


def test_camera_amazing_but_battery_terrible_with_the_real_model(analyzer):
    (analysis,) = analyze_items(
        [
            ItemText(
                "Samsung Galaxy S25 Ultra",
                "The camera is amazing but battery life is terrible",
            )
        ],
        BrandProfile("Samsung"),
        analyzer,
    )
    aspects = {a.aspect: a.sentiment for a in analysis.aspects}
    assert aspects["camera"] is Sentiment.positive
    assert aspects["battery"] is Sentiment.negative


def test_probabilities_are_valid_and_deterministic(analyzer):
    texts = ["fine I guess", "great", "terrible"]
    first = analyzer.analyze(texts)
    assert first == analyzer.analyze(texts)
    for result in first:
        assert (
            abs(result.positive_prob + result.neutral_prob + result.negative_prob - 1)
            < 1e-6
        )
