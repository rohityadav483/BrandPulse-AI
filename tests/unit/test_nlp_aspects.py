"""nlp/aspects + config/taxonomy: lexicon aspect detection mapped to clauses."""

import pytest

from app.config.taxonomy import LEXICON_VERSION, LEXICONS, get_lexicon
from app.schemas.domain import Category
from app.services.nlp.aspects import (
    AspectClause,
    aspect_names,
    detect_aspects,
    detect_aspects_in_text,
    terms_in_text,
)
from app.services.nlp.clauses import Clause, split_clauses
from app.services.nlp.textnorm import normalize_text

ELECTRONICS_ASPECTS = {
    "battery",
    "charging",
    "camera",
    "display",
    "performance",
    "price",
    "design",
    "software",
    "customer_support",
    "audio",
    "connectivity",
}


# --- taxonomy -------------------------------------------------------------------------------


def test_presets_cover_every_category_value():
    assert set(LEXICONS) == {category.value for category in Category}


def test_consumer_electronics_has_the_required_aspects():
    assert set(get_lexicon(Category.consumer_electronics)) == ELECTRONICS_ASPECTS


def test_default_category_is_consumer_electronics():
    assert get_lexicon() is get_lexicon(Category.consumer_electronics)
    assert get_lexicon("consumer_electronics") is get_lexicon(Category.consumer_electronics)


def test_generic_preset_is_separate_and_nonempty():
    generic = get_lexicon(Category.generic)
    assert generic and set(generic) != ELECTRONICS_ASPECTS
    assert "battery" not in generic


def test_unknown_category_is_rejected():
    with pytest.raises(ValueError, match="unknown category"):
        get_lexicon("toys")


@pytest.mark.parametrize("category", list(Category))
def test_lexicon_is_well_formed(category):
    lexicon = get_lexicon(category)
    seen_in = {}
    for aspect, terms in lexicon.items():
        assert aspect == aspect.casefold() and " " not in aspect
        assert terms, aspect
        assert len(set(terms)) == len(terms), f"duplicate term in {aspect}"
        for term in terms:
            assert normalize_text(term), f"{aspect}: {term!r} normalises to nothing"
            assert term == term.casefold(), f"{aspect}: {term!r} is not lowercase"
            seen_in.setdefault(normalize_text(term), set()).add(aspect)
    shared = {term: aspects for term, aspects in seen_in.items() if len(aspects) > 1}
    assert not shared, f"term listed under several aspects: {shared}"


def test_lexicons_are_read_only():
    lexicon = get_lexicon(Category.consumer_electronics)
    with pytest.raises(TypeError):
        lexicon["new_aspect"] = ("x",)  # type: ignore[index]
    with pytest.raises(TypeError):
        LEXICONS["toys"] = lexicon  # type: ignore[index]


def test_lexicon_version_is_set():
    assert LEXICON_VERSION.startswith("lex-")


# --- term matching --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text,aspect",
    [
        ("The battery lasts two days", "battery"),
        ("battery-life is great", "battery"),
        ("Phone drains overnight", "battery"),
        ("Fast charging is quick", "charging"),
        ("The charger is included", "charging"),
        ("Photos look sharp", "camera"),
        ("Great selfie quality", "camera"),
        ("Low light shots are noisy", "camera"),
        ("The AMOLED panel is bright", "display"),
        ("Screen has a 120 Hz refresh rate", "display"),
        ("It stutters when multitasking", "performance"),
        ("Gets very laggy", "performance"),
        ("Overheating while gaming", "performance"),
        ("Way too expensive", "price"),
        ("Good value for money", "price"),
        ("Premium titanium design", "design"),
        ("Very lightweight", "design"),
        ("One UI is smooth", "software"),
        ("Buggy firmware", "software"),
        ("Too many bugs", "software"),
        ("Android 16 is out", "software"),
        ("Customer service was rude", "customer_support"),
        ("Warranty claim denied", "customer_support"),
        ("Speaker is tinny", "audio"),
        ("Wi-Fi keeps dropping", "connectivity"),
        ("Bluetooth pairing fails", "connectivity"),
        ("5G reception is weak", "connectivity"),
    ],
)
def test_terms_map_to_the_expected_aspect(text, aspect):
    assert aspect in terms_in_text(text)


@pytest.mark.parametrize(
    "text",
    [
        "I bought it yesterday",
        "Samsung announced a phone",
        "Apple pie recipe",  # "app" must not match inside "Apple"
        "Photograph of a sunset",  # "photo" is a whole-word term only
    ],
)
def test_text_without_aspect_terms_has_none(text):
    assert terms_in_text(text) == {}


def test_whole_words_only():
    assert terms_in_text("scrambling pricewaterhouse") == {}
    assert "battery" in terms_in_text("the battery-powered toy")


def test_plural_forms_match():
    assert "camera" in terms_in_text("Three cameras on the back")
    assert "software" in terms_in_text("many apps crash")
    assert "software" in terms_in_text("glitches everywhere")
    assert "price" in terms_in_text("prices went up")


def test_bare_update_is_not_a_software_term():
    assert terms_in_text("Battery drain since the update").keys() == {"battery"}
    assert "software" in terms_in_text("The software update changed things")


def test_matching_is_case_insensitive_and_reports_lexicon_terms():
    assert terms_in_text("BATTERY LIFE is bad") == {"battery": ("battery", "battery life")}


def test_matched_terms_are_in_lexicon_order():
    hits = terms_in_text("screen on time and battery life")["battery"]
    assert hits == ("battery", "battery life", "screen on time")


def test_empty_text_has_no_terms():
    assert terms_in_text("") == {}
    assert terms_in_text("  ...  ") == {}


def test_generic_category_uses_its_own_lexicon():
    assert terms_in_text("The battery is bad", Category.generic) == {}
    assert "quality" in terms_in_text("Flimsy quality", Category.generic)
    assert "delivery" in terms_in_text("Shipping took weeks", "generic")


# --- aspect to clause mapping ---------------------------------------------------------------


def pairs(text, category=Category.consumer_electronics):
    return [(found.aspect, found.clause.text) for found in detect_aspects_in_text(text, category)]


def test_each_aspect_is_mapped_to_its_own_clause():
    assert pairs("The camera is amazing but battery life is terrible") == [
        ("camera", "The camera is amazing"),
        ("battery", "battery life is terrible"),
    ]


def test_contrast_words_other_than_but_work_the_same():
    assert pairs("Great display however the price is steep") == [
        ("display", "Great display"),
        ("price", "the price is steep"),
    ]


def test_one_clause_can_carry_several_aspects():
    assert pairs("Battery and camera are both great") == [
        ("battery", "Battery and camera are both great"),
        ("camera", "Battery and camera are both great"),
    ]


def test_aspect_in_two_clauses_keeps_one_entry_the_richest_clause():
    found = detect_aspects_in_text("Battery is fine. The battery life and screen on time are bad")
    battery = [f for f in found if f.aspect == "battery"]
    assert len(battery) == 1
    assert battery[0].clause.text == "The battery life and screen on time are bad"
    assert battery[0].matched_terms == ("battery", "battery life", "screen on time")


def test_tie_goes_to_the_earliest_clause():
    found = detect_aspects_in_text("Battery is fine. Battery is bad")
    assert [f.clause.text for f in found] == ["Battery is fine"]


def test_results_are_ordered_by_clause_then_lexicon_order():
    found = detect_aspects_in_text("Camera and battery good but price and display bad")
    assert [f.aspect for f in found] == ["battery", "camera", "display", "price"]


def test_text_without_aspects_gives_empty_list():
    assert detect_aspects_in_text("I like it") == []
    assert detect_aspects_in_text(None) == []
    assert detect_aspects([]) == []


def test_detect_aspects_works_on_prebuilt_clauses():
    clauses = [Clause("battery died", 0, 0), Clause("camera ok", 1, 0)]
    assert detect_aspects(clauses) == [
        AspectClause("battery", clauses[0], ("battery",)),
        AspectClause("camera", clauses[1], ("camera",)),
    ]


def test_detect_matches_split_then_detect():
    text = "Screen is gorgeous but the software is buggy. Charger is slow"
    assert detect_aspects_in_text(text) == detect_aspects(split_clauses(text))


def test_aspect_names_follow_lexicon_order():
    assert aspect_names()[0] == "battery"
    assert set(aspect_names()) == ELECTRONICS_ASPECTS
    assert aspect_names("generic") == tuple(get_lexicon("generic"))


def test_unknown_category_is_rejected_by_detection():
    with pytest.raises(ValueError):
        detect_aspects_in_text("battery", "toys")
