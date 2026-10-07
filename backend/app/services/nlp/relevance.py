"""Rule-based brand relevance: does an item talk about the brand? Pure, no I/O.

An item is about the brand when the brand name, a product name or an alias appears in its
title or snippet, as whole words, ignoring case, punctuation and spacing
(`galaxy-s25 ULTRA` matches `Galaxy S25 Ultra`; `Samsung's` matches `Samsung`).
Terms are matched exactly as configured: nothing is derived (`S25 Ultra` does not match a
configured `Galaxy S25 Ultra` unless it is also listed as an alias).
"""

from collections.abc import Iterable
from dataclasses import dataclass

from app.services.nlp.textnorm import normalize_text

RELEVANCE_RULES_VERSION = "relevance-1"


def _clean_terms(values: Iterable[str], field: str) -> tuple[str, ...]:
    if isinstance(values, str):
        raise TypeError(f"{field} must be a sequence of strings, not a single string")
    cleaned: list[str] = []
    for value in values:
        if not isinstance(value, str):
            raise TypeError(
                f"{field} entries must be strings, got {type(value).__name__}"
            )
        stripped = value.strip()
        if stripped:
            cleaned.append(stripped)
    return tuple(cleaned)


@dataclass(frozen=True, slots=True)
class BrandProfile:
    """Terms that identify one brand. `brand` is required; products and aliases are optional."""

    brand: str
    products: tuple[str, ...] = ()
    aliases: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.brand, str) or not normalize_text(self.brand):
            raise ValueError("brand must contain at least one letter or digit")
        object.__setattr__(self, "brand", self.brand.strip())
        object.__setattr__(self, "products", _clean_terms(self.products, "products"))
        object.__setattr__(self, "aliases", _clean_terms(self.aliases, "aliases"))

    @property
    def terms(self) -> tuple[str, ...]:
        """Brand, products, aliases in that order, as configured. Entries that normalise to
        nothing (`"!!!"`) are dropped and entries equal after normalisation are kept once."""
        seen: set[str] = set()
        out: list[str] = []
        for term in (self.brand, *self.products, *self.aliases):
            key = normalize_text(term)
            if key and key not in seen:
                seen.add(key)
                out.append(term)
        return tuple(out)


@dataclass(frozen=True, slots=True)
class RelevanceResult:
    is_about_brand: bool
    matched_terms: tuple[str, ...]  # configured spelling, in `BrandProfile.terms` order
    in_title: bool
    in_snippet: bool


def _contains(padded_text: str, normalized_term: str) -> bool:
    return f" {normalized_term} " in padded_text


def detect_relevance(
    profile: BrandProfile, title: str | None, snippet: str | None = None
) -> RelevanceResult:
    """Match the profile's terms against the title and the snippet."""
    padded_title = f" {normalize_text(title)} "
    padded_snippet = f" {normalize_text(snippet)} "
    matched: list[str] = []
    in_title = False
    in_snippet = False
    for term in profile.terms:
        key = normalize_text(term)
        hit_title = _contains(padded_title, key)
        hit_snippet = _contains(padded_snippet, key)
        if hit_title or hit_snippet:
            matched.append(term)
            in_title = in_title or hit_title
            in_snippet = in_snippet or hit_snippet
    return RelevanceResult(
        is_about_brand=bool(matched),
        matched_terms=tuple(matched),
        in_title=in_title,
        in_snippet=in_snippet,
    )
