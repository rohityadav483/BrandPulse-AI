"""nlp/relevance: rule-based brand, product and alias matching."""

import pytest

from app.services.nlp.relevance import BrandProfile, RelevanceResult, detect_relevance

SAMSUNG = BrandProfile(
    brand="Samsung",
    products=("Galaxy S25 Ultra",),
    aliases=("S25 Ultra", "Sammy"),
)


def test_brand_name_in_title_matches():
    result = detect_relevance(SAMSUNG, "Samsung announces new update", None)
    assert result == RelevanceResult(True, ("Samsung",), True, False)


def test_product_in_snippet_matches():
    result = detect_relevance(SAMSUNG, "Phone review", "The Galaxy S25 Ultra is fast.")
    assert result.is_about_brand
    # The alias "S25 Ultra" also appears inside "Galaxy S25 Ultra", so both match.
    assert result.matched_terms == ("Galaxy S25 Ultra", "S25 Ultra")
    assert (result.in_title, result.in_snippet) == (False, True)


def test_alias_matches():
    result = detect_relevance(SAMSUNG, "My S25 Ultra battery", "")
    assert result.matched_terms == ("S25 Ultra",)


def test_matched_terms_follow_profile_order_and_configured_spelling():
    result = detect_relevance(SAMSUNG, "sammy and SAMSUNG", "galaxy s25 ultra")
    assert result.matched_terms == ("Samsung", "Galaxy S25 Ultra", "S25 Ultra", "Sammy")


def test_title_and_snippet_flags_are_independent():
    result = detect_relevance(SAMSUNG, "Samsung news", "Samsung says more")
    assert (result.in_title, result.in_snippet) == (True, True)
    assert result.matched_terms == ("Samsung",)


@pytest.mark.parametrize(
    "title",
    [
        "SAMSUNG",
        "samsung",
        "Samsung's new phone",
        "Samsung, Apple and OnePlus",
        "(Samsung)",
        "Review: Samsung!",
    ],
)
def test_case_and_punctuation_do_not_matter(title):
    assert detect_relevance(SAMSUNG, title, None).is_about_brand


@pytest.mark.parametrize(
    "title",
    ["galaxy-s25-ultra review", "Galaxy   S25\tUltra", "GALAXY S25 ULTRA!!", "galaxy s25 ultra"],
)
def test_product_spelling_variants_match(title):
    result = detect_relevance(SAMSUNG, title, None)
    assert result.matched_terms == ("Galaxy S25 Ultra", "S25 Ultra")


@pytest.mark.parametrize(
    "title",
    ["Samsungite fans", "Anti-Samsungs", "Samsung2", "Pre-samsungish"],
)
def test_partial_words_do_not_match(title):
    # "Anti-Samsungs": normalised to "anti samsungs", not the word "samsung".
    assert not detect_relevance(SAMSUNG, title, None).is_about_brand


def test_unrelated_item_is_not_about_brand():
    result = detect_relevance(SAMSUNG, "Best budget phones of the year", "Apple and OnePlus.")
    assert result == RelevanceResult(False, (), False, False)


def test_product_is_not_derived_from_a_longer_configured_name():
    profile = BrandProfile(brand="Samsung", products=("Galaxy S25 Ultra",))
    assert not detect_relevance(profile, "S25 Ultra review", None).is_about_brand


@pytest.mark.parametrize("title,snippet", [(None, None), ("", ""), ("   ", None), (None, "")])
def test_missing_text_is_not_about_brand(title, snippet):
    assert not detect_relevance(SAMSUNG, title, snippet).is_about_brand


def test_snippet_is_optional():
    assert detect_relevance(SAMSUNG, "Samsung").is_about_brand


def test_blank_and_duplicate_terms_are_ignored():
    profile = BrandProfile(brand=" Samsung ", products=("", "  ", "samsung"), aliases=("!!!",))
    assert profile.brand == "Samsung"
    assert profile.terms == ("Samsung",)
    assert not detect_relevance(profile, "!!! only punctuation", None).is_about_brand


def test_profile_accepts_lists_and_stores_tuples():
    profile = BrandProfile(brand="Apple", products=["iPhone 17"], aliases=["AAPL"])
    assert profile.products == ("iPhone 17",)
    assert profile.aliases == ("AAPL",)


@pytest.mark.parametrize("brand", ["", "   ", "!!!", "—"])
def test_brand_must_have_letters_or_digits(brand):
    with pytest.raises(ValueError):
        BrandProfile(brand=brand)


def test_single_string_for_products_is_rejected():
    with pytest.raises(TypeError):
        BrandProfile(brand="Samsung", products="Galaxy")  # type: ignore[arg-type]


def test_non_string_term_is_rejected():
    with pytest.raises(TypeError):
        BrandProfile(brand="Samsung", aliases=(5,))  # type: ignore[arg-type]


def test_profile_is_immutable():
    with pytest.raises(AttributeError):
        SAMSUNG.brand = "Other"  # type: ignore[misc]


def test_detection_is_deterministic():
    first = detect_relevance(SAMSUNG, "Samsung S25 Ultra", "Galaxy S25 Ultra")
    assert first == detect_relevance(SAMSUNG, "Samsung S25 Ultra", "Galaxy S25 Ultra")
