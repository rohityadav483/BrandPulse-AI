"""nlp/clauses: sentence split, then contrast-word split."""

import pytest

from app.services.nlp.clauses import Clause, split_clauses


def texts(value):
    return [clause.text for clause in split_clauses(value)]


@pytest.mark.parametrize(
    "text,expected",
    [
        (
            "The camera is amazing but battery life is terrible",
            ["The camera is amazing", "battery life is terrible"],
        ),
        (
            "The screen is gorgeous however the battery is weak",
            ["The screen is gorgeous", "the battery is weak"],
        ),
        (
            "Great performance although the price is high",
            ["Great performance", "the price is high"],
        ),
        (
            "Good camera though the battery is poor",
            ["Good camera", "the battery is poor"],
        ),
        (
            "Nice display even though the software is buggy",
            ["Nice display", "the software is buggy"],
        ),
        (
            "Fast phone whereas the camera is average",
            ["Fast phone", "the camera is average"],
        ),
        (
            "Nice design nevertheless the speaker is bad",
            ["Nice design", "the speaker is bad"],
        ),
        (
            "Bright screen on the other hand the battery drains",
            ["Bright screen", "the battery drains"],
        ),
    ],
)
def test_contrast_words_split_and_are_removed(text, expected):
    assert texts(text) == expected


@pytest.mark.parametrize("word", ["BUT", "But", "bUt"])
def test_contrast_is_case_insensitive_and_text_case_is_kept(word):
    assert texts(f"Camera is Great {word} Battery is Bad") == [
        "Camera is Great",
        "Battery is Bad",
    ]


def test_comma_before_contrast_word_is_trimmed():
    assert texts("The camera is amazing, but the battery is terrible") == [
        "The camera is amazing",
        "the battery is terrible",
    ]


def test_sentence_starting_with_contrast_word():
    assert texts("The phone is great. However, the battery is bad.") == [
        "The phone is great",
        "the battery is bad",
    ]
    assert texts("But the battery is bad") == ["the battery is bad"]


def test_several_contrasts_in_one_sentence():
    assert texts("Camera great but battery bad however screen fine") == [
        "Camera great",
        "battery bad",
        "screen fine",
    ]


@pytest.mark.parametrize(
    "text,expected",
    [
        (
            "Great screen, while the battery is poor",
            ["Great screen", "the battery is poor"],
        ),
        ("Cheap, yet very fast", ["Cheap", "very fast"]),
        (
            "Phone is great, YET the battery is bad",
            ["Phone is great", "the battery is bad"],
        ),
    ],
)
def test_while_and_yet_split_only_after_a_comma(text, expected):
    assert texts(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "Phone gets hot while charging",
        "Not available yet",
        "While the camera is great the battery is bad",
        "It is not yet released",
    ],
)
def test_bare_while_and_yet_do_not_split(text):
    assert texts(text) == [text]


@pytest.mark.parametrize(
    "text",
    [
        "Not only fast but also cheap",
        "Nothing but problems",
        "It is all but dead",
        "Anything but great",
        "It acts as though it is broken",
    ],
)
def test_non_contrast_uses_do_not_split(text):
    assert texts(text) == [text]


def test_trailing_contrast_word_leaves_the_clause():
    assert texts("The camera is good though.") == ["The camera is good"]


def test_sentences_split_on_terminators():
    assert texts("Battery is bad. Camera is good! Is price fair? Yes") == [
        "Battery is bad",
        "Camera is good",
        "Is price fair",
        "Yes",
    ]


def test_ellipsis_and_semicolon_and_newline_split():
    assert texts("Battery drains fast ... camera is fine") == [
        "Battery drains fast",
        "camera is fine",
    ]
    assert texts("Battery drains fast… camera is fine") == [
        "Battery drains fast",
        "camera is fine",
    ]
    assert texts("Battery bad; camera good") == ["Battery bad", "camera good"]
    assert texts("Battery bad\nCamera good") == ["Battery bad", "Camera good"]


def test_numbers_and_abbreviations_do_not_end_a_sentence():
    assert texts("The 6.8 inch screen beats the 6.1 inch one") == [
        "The 6.8 inch screen beats the 6.1 inch one"
    ]
    assert texts("Faster vs. last year, e.g. the chip is better") == [
        "Faster vs. last year, e.g. the chip is better"
    ]


def test_indexes_are_sequential_and_sentence_index_tracks_sentences():
    clauses = split_clauses("Camera great but battery bad. Price is high! Screen fine")
    assert [(c.text, c.index, c.sentence_index) for c in clauses] == [
        ("Camera great", 0, 0),
        ("battery bad", 1, 0),
        ("Price is high", 2, 1),
        ("Screen fine", 3, 2),
    ]


def test_sentence_index_skips_sentences_that_produce_no_clause():
    clauses = split_clauses("Good. ... However. Bad")
    assert [(c.text, c.sentence_index) for c in clauses] == [("Good", 0), ("Bad", 1)]


@pytest.mark.parametrize(
    "value", [None, "", "   ", "\n\t", "...", "!!!", "But", "However,", ", ;"]
)
def test_nothing_to_split_gives_no_clauses(value):
    assert split_clauses(value) == []


def test_whitespace_is_collapsed_inside_a_clause():
    assert texts("  The   camera \t is   great   but   battery  bad ") == [
        "The camera is great",
        "battery bad",
    ]


def test_clause_is_immutable_value():
    clause = split_clauses("Battery bad")[0]
    assert clause == Clause("Battery bad", 0, 0)
    with pytest.raises(AttributeError):
        clause.text = "x"  # type: ignore[misc]


def test_split_is_deterministic():
    text = "Camera great but battery bad. However, price is high"
    assert split_clauses(text) == split_clauses(text)
