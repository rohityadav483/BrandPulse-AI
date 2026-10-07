"""Deterministic keyword and topic rules (Phase 4.3). Pure: no model, no DB."""

import pytest

from app.services.nlp.keywords import (
    KEYWORD_RULES_VERSION,
    MAX_WORD_LENGTH,
    STOPWORDS,
    extract_keywords,
)
from app.services.nlp.topics import TOPIC_RULES_VERSION, derive_topics

# ---- keywords ----


def test_frequency_then_first_position_then_alphabet():
    text = "battery drain after update. update again, battery drain, update"
    assert extract_keywords(text) == ("update", "battery", "drain")


def test_ties_keep_first_position():
    assert extract_keywords("zebra apple mango") == ("zebra", "apple", "mango")


def test_stopwords_short_words_and_digits_are_dropped():
    assert extract_keywords("The 5G is up to 20 and it is ok") == ()
    assert extract_keywords("the and of in on") == ()


def test_brand_terms_are_excluded_word_by_word():
    text = "Samsung Galaxy S25 Ultra camera review"
    assert extract_keywords(text, exclude_terms=["Samsung", "Galaxy S25 Ultra"]) == (
        "camera",
        "review",
    )
    assert "samsung" in extract_keywords(text)


def test_casefold_and_punctuation_are_normalised():
    assert extract_keywords("Battery! BATTERY? battery-life") == ("battery", "life")


def test_contractions_do_not_leak_fragments():
    assert extract_keywords("don't isn't won't") == ()


@pytest.mark.parametrize("text", [None, "", "   ", "!!! ???"])
def test_blank_or_wordless_text_gives_nothing(text):
    assert extract_keywords(text) == ()


def test_max_keywords_limits_and_zero_gives_nothing():
    text = "alpha bravo charlie delta echo foxtrot golf"
    assert extract_keywords(text) == ("alpha", "bravo", "charlie", "delta", "echo")
    assert extract_keywords(text, max_keywords=2) == ("alpha", "bravo")
    assert extract_keywords(text, max_keywords=0) == ()


def test_overlong_words_are_dropped():
    assert extract_keywords("x" * (MAX_WORD_LENGTH + 1) + " valid") == ("valid",)


def test_result_depends_on_the_text_only():
    text = "camera zoom camera lens"
    assert (
        extract_keywords(text) == extract_keywords(text) == ("camera", "zoom", "lens")
    )


def test_bad_arguments():
    with pytest.raises(TypeError):
        extract_keywords("text", exclude_terms="samsung")
    with pytest.raises(ValueError):
        extract_keywords("text", max_keywords=-1)


def test_stopwords_are_lowercase_single_words():
    assert all(word == word.lower() and word.isalpha() for word in STOPWORDS)


def test_rule_versions_are_set():
    assert KEYWORD_RULES_VERSION == "keywords-1" and TOPIC_RULES_VERSION == "topics-1"


# ---- topics ----


def test_aspects_first_then_uncovered_keywords():
    assert derive_topics(["camera", "battery"], ["review", "owners"]) == (
        "camera",
        "battery",
        "review",
        "owners",
    )


def test_keywords_covered_by_an_aspect_are_not_repeated():
    topics = derive_topics(
        ["battery"],
        ["battery", "drain", "update"],
        covered_terms=["battery", "drain"],
    )
    assert topics == ("battery", "update")


def test_covered_multiword_terms_cover_their_words():
    assert derive_topics(
        ["battery"], ["life", "july"], covered_terms=["battery life"]
    ) == (
        "battery",
        "july",
    )


def test_keyword_topics_are_capped():
    keywords = ["one1", "two2", "three", "four"]
    assert derive_topics([], keywords) == ("one1", "two2", "three")
    assert derive_topics([], keywords, max_keyword_topics=1) == ("one1",)
    assert derive_topics(["camera"], keywords, max_keyword_topics=0) == ("camera",)


def test_duplicates_are_removed_and_order_is_kept():
    assert derive_topics(["camera", "camera", "price"], ["price", "zoom"]) == (
        "camera",
        "price",
        "zoom",
    )


def test_nothing_in_nothing_out():
    assert derive_topics([], []) == ()


def test_topics_bad_arguments():
    with pytest.raises(TypeError):
        derive_topics("camera", [])
    with pytest.raises(TypeError):
        derive_topics([], "review")
    with pytest.raises(TypeError):
        derive_topics([], [], covered_terms="battery")
    with pytest.raises(ValueError):
        derive_topics([], [], max_keyword_topics=-1)
