"""Aspect lexicons per category preset (docs/ARCHITECTURE.md section 5.1, API.md section 3.1).

Pure data. A lexicon maps an aspect name to the terms that signal it. Terms are matched on
whole words after normalisation (casefold, punctuation collapsed to spaces), and a trailing
plural `s`/`es` is accepted, so list singular forms only. An aspect name is what ends up in
`item_aspects.aspect` and in the API, so renaming one is a contract change.

Deliberately left out because they are too ambiguous to decide an aspect on their own:
bare `update` (only `software update`, `firmware` etc. count), `slow`/`fast` (they describe
charging as often as performance), `support` (only `customer support` etc.), `signal`, `look`,
`build`, `heavy`. Recall on these is a known limitation to evaluate against real snippets.

Changing any term or aspect changes analysis results: bump `LEXICON_VERSION` (it is part of
the later `analyzer_version`).
"""

from collections.abc import Mapping
from types import MappingProxyType

from app.schemas.domain import Category

LEXICON_VERSION = "lex-1"

Lexicon = Mapping[str, tuple[str, ...]]

_CONSUMER_ELECTRONICS: dict[str, tuple[str, ...]] = {
    "battery": (
        "battery",
        "battery life",
        "battery drain",
        "battery health",
        "drain",
        "draining",
        "screen on time",
        "standby",
        "mah",
        "power consumption",
    ),
    "charging": (
        "charging",
        "charger",
        "charge",
        "fast charging",
        "wireless charging",
        "charging speed",
        "power adapter",
    ),
    "camera": (
        "camera",
        "photo",
        "picture",
        "photography",
        "selfie",
        "zoom",
        "lens",
        "megapixel",
        "night mode",
        "low light",
        "autofocus",
        "video recording",
    ),
    "display": (
        "display",
        "screen",
        "brightness",
        "oled",
        "amoled",
        "refresh rate",
        "resolution",
        "bezel",
        "touchscreen",
        "screen protector",
    ),
    "performance": (
        "performance",
        "processor",
        "chipset",
        "cpu",
        "gpu",
        "ram",
        "benchmark",
        "fps",
        "lag",
        "laggy",
        "stutter",
        "sluggish",
        "freeze",
        "freezing",
        "overheat",
        "overheating",
        "throttling",
        "multitasking",
        "gaming",
    ),
    "price": (
        "price",
        "pricing",
        "priced",
        "overpriced",
        "pricey",
        "expensive",
        "cheap",
        "affordable",
        "cost",
        "value for money",
        "worth the money",
        "discount",
    ),
    "design": (
        "design",
        "aesthetic",
        "build quality",
        "finish",
        "titanium",
        "aluminum",
        "aluminium",
        "weight",
        "lightweight",
        "slim",
        "thickness",
        "form factor",
        "colour",
        "color",
    ),
    "software": (
        "software",
        "software update",
        "firmware",
        "one ui",
        "android",
        "ios",
        "operating system",
        "os",
        "interface",
        "app",
        "bug",
        "buggy",
        "glitch",
        "bloatware",
        "patch",
    ),
    "customer_support": (
        "customer support",
        "customer service",
        "technical support",
        "tech support",
        "support team",
        "warranty",
        "service center",
        "repair",
        "refund",
        "replacement",
    ),
    "audio": (
        "audio",
        "speaker",
        "sound quality",
        "microphone",
        "call quality",
        "headphone jack",
        "noise cancellation",
    ),
    "connectivity": (
        "connectivity",
        "wifi",
        "wi fi",
        "bluetooth",
        "5g",
        "lte",
        "reception",
        "nfc",
        "gps",
    ),
}

_GENERIC: dict[str, tuple[str, ...]] = {
    "quality": (
        "quality",
        "durable",
        "durability",
        "flimsy",
        "well made",
        "poorly made",
    ),
    "price": (
        "price",
        "pricing",
        "overpriced",
        "pricey",
        "expensive",
        "cheap",
        "affordable",
        "cost",
        "value for money",
    ),
    "design": ("design", "aesthetic", "look and feel", "style", "appearance"),
    "customer_support": (
        "customer support",
        "customer service",
        "support team",
        "warranty",
        "refund",
        "replacement",
        "return policy",
    ),
    "reliability": (
        "reliable",
        "reliability",
        "unreliable",
        "broke",
        "broken",
        "defective",
    ),
    "usability": (
        "usability",
        "easy to use",
        "hard to use",
        "intuitive",
        "user friendly",
    ),
    "delivery": ("delivery", "shipping", "arrived late", "packaging"),
}

LEXICONS: Mapping[str, Lexicon] = MappingProxyType(
    {
        Category.consumer_electronics.value: MappingProxyType(_CONSUMER_ELECTRONICS),
        Category.generic.value: MappingProxyType(_GENERIC),
    }
)

DEFAULT_CATEGORY = Category.consumer_electronics


def get_lexicon(category: Category | str = DEFAULT_CATEGORY) -> Lexicon:
    """Aspect lexicon for a category preset. Unknown category -> ValueError."""
    key = category.value if isinstance(category, Category) else category
    try:
        return LEXICONS[key]
    except KeyError:
        known = ", ".join(sorted(LEXICONS))
        raise ValueError(f"unknown category {category!r}; known: {known}") from None
