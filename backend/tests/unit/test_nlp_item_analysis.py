"""item_analysis, analyzer_version and the persisted value types. Stub analyzer, no DB, no model."""

import pytest
from pydantic import ValidationError

from app.config.taxonomy import LEXICON_VERSION
from app.db.models import enums as db_enums
from app.schemas import domain
from app.schemas.nlp import (
    AspectSentiment,
    ItemAnalysis,
    NewItemAnalysis,
    ReuseTarget,
)
from app.services.nlp.analyzer_version import (
    analyzer_version_for,
    build_analyzer_version,
)
from app.services.nlp.clauses import CLAUSE_RULES_VERSION
from app.services.nlp.item_analysis import ItemText, analyze_items, full_text
from app.services.nlp.keywords import KEYWORD_RULES_VERSION
from app.services.nlp.relevance import RELEVANCE_RULES_VERSION, BrandProfile
from app.services.nlp.sentiment import SentimentResult, StubSentimentAnalyzer
from app.services.nlp.topics import TOPIC_RULES_VERSION

SAMSUNG = BrandProfile("Samsung", products=("Galaxy S25 Ultra",))
HASH = "a" * 64


class CountingAnalyzer(StubSentimentAnalyzer):
    def __init__(self):
        self.calls: list[list[str]] = []

    def analyze(self, texts):
        self.calls.append(list(texts))
        return super().analyze(texts)


# ---- the PRD example, end to end through the stub ----


def test_camera_amazing_but_battery_terrible():
    (analysis,) = analyze_items(
        [
            ItemText(
                "Samsung Galaxy S25 Ultra review",
                "The camera is amazing but battery life is terrible",
            )
        ],
        SAMSUNG,
        StubSentimentAnalyzer(),
    )
    aspects = {a.aspect: a for a in analysis.aspects}
    assert analysis.is_about_brand and analysis.matched_terms == (
        "Samsung",
        "Galaxy S25 Ultra",
    )
    assert aspects["camera"].sentiment is domain.Sentiment.positive
    assert aspects["camera"].clause == "The camera is amazing"
    assert aspects["battery"].sentiment is domain.Sentiment.negative
    assert aspects["battery"].clause == "battery life is terrible"
    assert aspects["battery"].negative_prob > aspects["camera"].negative_prob
    assert aspects["battery"].score < 0 < aspects["camera"].score


def test_overall_fields_come_from_the_overall_sentiment_result():
    analyzer = StubSentimentAnalyzer()
    item = ItemText("Samsung phone is great", "Really great and reliable")
    (analysis,) = analyze_items([item], SAMSUNG, analyzer)
    (expected,) = analyzer.analyze([full_text(item)])
    assert analysis.sentiment is expected.label is domain.Sentiment.positive
    assert analysis.sentiment_score == expected.score
    assert analysis.negative_prob == expected.negative_prob
    assert analysis.model == analyzer.model_name


# ---- relevance gate ----


def test_irrelevant_items_get_a_neutral_row_and_no_inference():
    analyzer = CountingAnalyzer()
    (analysis,) = analyze_items(
        [ItemText("Best pizza", "Great battery of ovens")], SAMSUNG, analyzer
    )
    assert not analysis.is_about_brand
    assert (analysis.sentiment, analysis.sentiment_score, analysis.negative_prob) == (
        domain.Sentiment.neutral,
        0.0,
        0.0,
    )
    assert analysis.matched_terms == () and analysis.aspects == ()
    assert analyzer.calls == []  # not even an empty call
    assert analysis.analyzer_version == analyzer_version_for(analyzer)


def test_mixed_batch_is_one_analyzer_call_and_keeps_item_order():
    analyzer = CountingAnalyzer()
    items = [
        ItemText("Samsung is great", None),
        ItemText("Unrelated", "nothing"),
        ItemText("Samsung battery is terrible", "Camera is amazing"),
    ]
    analyses = analyze_items(items, SAMSUNG, analyzer)
    assert len(analyzer.calls) == 1
    assert [a.is_about_brand for a in analyses] == [True, False, True]
    assert analyses[0].sentiment is domain.Sentiment.positive
    assert {a.aspect for a in analyses[2].aspects} == {"battery", "camera"}
    # every text the model saw belongs to a relevant item (overall text + aspect clauses)
    assert all("Unrelated" not in text for text in analyzer.calls[0])


def test_no_items_means_no_call_and_no_result():
    analyzer = CountingAnalyzer()
    assert analyze_items([], SAMSUNG, analyzer) == []
    assert analyzer.calls == []


def test_analyzer_returning_the_wrong_number_of_results_is_an_error():
    class Broken(StubSentimentAnalyzer):
        def analyze(self, texts):
            return super().analyze(texts)[:-1]

    with pytest.raises(ValueError, match="results"):
        analyze_items([ItemText("Samsung camera is great", None)], SAMSUNG, Broken())


def test_item_without_aspects_has_none():
    (analysis,) = analyze_items(
        [ItemText("Samsung announces event", "Next week")],
        SAMSUNG,
        StubSentimentAnalyzer(),
    )
    assert analysis.is_about_brand and analysis.aspects == ()


def test_category_selects_the_lexicon():
    item = ItemText("Samsung support", "Delivery was late")
    generic = analyze_items([item], SAMSUNG, StubSentimentAnalyzer(), "generic")[0]
    electronics = analyze_items(
        [item], SAMSUNG, StubSentimentAnalyzer(), "consumer_electronics"
    )[0]
    assert "delivery" in {a.aspect for a in generic.aspects}
    assert "delivery" not in {a.aspect for a in electronics.aspects}
    assert generic.analyzer_version != electronics.analyzer_version


def test_keywords_and_topics_are_filled_for_relevant_items():
    (analysis,) = analyze_items(
        [
            ItemText(
                "Samsung camera great", "Battery drain after the update, battery drain"
            )
        ],
        SAMSUNG,
        StubSentimentAnalyzer(),
    )
    # brand word excluded; most frequent first; topics = aspects (in text order) then keywords
    assert analysis.keywords[:2] == ("battery", "drain")
    assert "samsung" not in analysis.keywords
    assert analysis.topics[:2] == ("camera", "battery")
    assert "update" in analysis.topics
    assert "drain" not in analysis.topics  # covered by the battery aspect


def test_irrelevant_items_get_no_keywords_or_topics():
    (analysis,) = analyze_items(
        [ItemText("Weather today", "Sunny with light wind")],
        SAMSUNG,
        StubSentimentAnalyzer(),
    )
    assert analysis.keywords == () and analysis.topics == ()


def test_keywords_do_not_depend_on_the_rest_of_the_batch():
    item = ItemText("Samsung camera great", "battery terrible after the update")
    alone = analyze_items([item], SAMSUNG, StubSentimentAnalyzer())[0]
    batched = analyze_items(
        [ItemText("Samsung display awful", "bright"), item],
        SAMSUNG,
        StubSentimentAnalyzer(),
    )[1]
    assert (alone.keywords, alone.topics) == (batched.keywords, batched.topics)


@pytest.mark.parametrize(
    ("title", "snippet", "expected"),
    [
        ("Title", "Snippet", "Title. Snippet"),
        ("Title.", "Snippet", "Title. Snippet"),
        ("Why?", "Because", "Why? Because"),
        ("Title", None, "Title"),
        ("Title", "   ", "Title"),
        ("", "Snippet", "Snippet"),
        ("  Title  ", "  Snippet ", "Title. Snippet"),
    ],
)
def test_full_text(title, snippet, expected):
    assert full_text(ItemText(title, snippet)) == expected


def test_analysis_is_deterministic():
    items = [ItemText("Samsung camera great", "battery terrible")]
    assert analyze_items(items, SAMSUNG, StubSentimentAnalyzer()) == analyze_items(
        items, SAMSUNG, StubSentimentAnalyzer()
    )


# ---- analyzer_version ----


def test_version_is_model_plus_lexicon_plus_rules_plus_category():
    version = build_analyzer_version("org/m")
    assert version == (
        f"org/m|{LEXICON_VERSION}|{CLAUSE_RULES_VERSION}|"
        f"{RELEVANCE_RULES_VERSION}|{KEYWORD_RULES_VERSION}|"
        f"{TOPIC_RULES_VERSION}|consumer_electronics"
    )


@pytest.mark.parametrize(
    "other",
    [
        build_analyzer_version("org/other"),
        build_analyzer_version("org/m", "generic"),
        build_analyzer_version("org/m", config_tag="margin-0.3-len256"),
    ],
)
def test_any_change_gives_a_different_version(other):
    assert other != build_analyzer_version("org/m")


def test_version_changes_when_a_rule_version_changes(monkeypatch):
    before = build_analyzer_version("org/m")
    import app.services.nlp.analyzer_version as module

    monkeypatch.setattr(module, "LEXICON_VERSION", "lex-2")
    assert module.build_analyzer_version("org/m") != before
    monkeypatch.setattr(module, "LEXICON_VERSION", LEXICON_VERSION)
    monkeypatch.setattr(module, "CLAUSE_RULES_VERSION", "clauses-2")
    assert module.build_analyzer_version("org/m") != before
    monkeypatch.setattr(module, "CLAUSE_RULES_VERSION", CLAUSE_RULES_VERSION)
    monkeypatch.setattr(module, "RELEVANCE_RULES_VERSION", "relevance-2")
    assert module.build_analyzer_version("org/m") != before
    monkeypatch.setattr(module, "RELEVANCE_RULES_VERSION", RELEVANCE_RULES_VERSION)
    monkeypatch.setattr(module, "KEYWORD_RULES_VERSION", "keywords-2")
    assert module.build_analyzer_version("org/m") != before
    monkeypatch.setattr(module, "KEYWORD_RULES_VERSION", KEYWORD_RULES_VERSION)
    monkeypatch.setattr(module, "TOPIC_RULES_VERSION", "topics-2")
    assert module.build_analyzer_version("org/m") != before


def test_version_uses_the_analyzers_config_tag_when_present():
    class Tagged(StubSentimentAnalyzer):
        config_tag = "margin-0.2-len256"

    assert analyzer_version_for(Tagged()).endswith("|margin-0.2-len256")
    assert not analyzer_version_for(StubSentimentAnalyzer()).endswith("len256")


def test_version_is_the_same_for_the_same_inputs():
    assert analyzer_version_for(StubSentimentAnalyzer()) == analyzer_version_for(
        StubSentimentAnalyzer()
    )


@pytest.mark.parametrize("model", ["", "  "])
def test_blank_model_name_is_rejected(model):
    with pytest.raises(ValueError):
        build_analyzer_version(model)


def test_separator_inside_a_part_is_rejected():
    with pytest.raises(ValueError):
        build_analyzer_version("org/m", config_tag="a|b")


# ---- persisted value types ----


def aspect(**overrides):
    values = {
        "aspect": "battery",
        "clause": "battery life is terrible",
        "sentiment": domain.Sentiment.negative,
        "negative_prob": 0.9,
        "score": -0.8,
    }
    return AspectSentiment(**(values | overrides))


def analysis(**overrides):
    values = {
        "sentiment": domain.Sentiment.negative,
        "sentiment_score": -0.5,
        "negative_prob": 0.7,
        "is_about_brand": True,
        "model": "m",
        "analyzer_version": "v",
    }
    return ItemAnalysis(**(values | overrides))


@pytest.mark.parametrize(
    "overrides",
    [
        {"negative_prob": 1.1},
        {"negative_prob": -0.1},
        {"score": 1.5},
        {"score": -1.5},
        {"aspect": " "},
        {"clause": ""},
    ],
)
def test_aspect_sentiment_validates(overrides):
    with pytest.raises(ValidationError):
        aspect(**overrides)


@pytest.mark.parametrize(
    "overrides",
    [
        {"sentiment_score": 2.0},
        {"negative_prob": -1.0},
        {"model": " "},
        {"analyzer_version": ""},
        {"aspects": (aspect(), aspect(clause="another clause"))},  # same aspect twice
    ],
)
def test_item_analysis_validates(overrides):
    with pytest.raises(ValidationError):
        analysis(**overrides)


@pytest.mark.parametrize("bad_hash", ["", "A" * 64, "a" * 63, "g" * 64])
def test_hash_must_be_lowercase_sha256_hex(bad_hash):
    import uuid

    with pytest.raises(ValidationError):
        NewItemAnalysis(
            content_id=uuid.uuid4(), content_hash=bad_hash, analysis=analysis()
        )
    with pytest.raises(ValidationError):
        ReuseTarget(content_id=uuid.uuid4(), content_hash=bad_hash)


def test_value_types_are_frozen():
    with pytest.raises(ValidationError):
        aspect().score = 0.0  # type: ignore[misc]


def test_db_enum_mirror_matches_the_domain_enum():
    assert [e.value for e in db_enums.Sentiment] == [e.value for e in domain.Sentiment]


def test_sentiment_result_still_has_the_phase_4_1_shape():
    result = SentimentResult(domain.Sentiment.neutral, 0.0, 1.0, 0.0)
    assert result.score == 0.0
