"""Text cleaning for SerpApi strings. Pure functions, no I/O.

Cleaning only removes noise (HTML, odd whitespace, invisible characters). It never rewrites
wording, case or punctuation: those are the job of `normalizer.normalize_for_match`, which
builds comparison keys but is never shown to users.
"""

import html
import re
import unicodedata

_TAG = re.compile(r"</?[A-Za-z][^>]*>")
_INVISIBLE = dict.fromkeys(
    map(
        ord,
        "\u00ad\u200b\u200c\u200d\u200e\u200f\u202a\u202b\u202c\u202d\u202e\u2060\ufeff",
    ),
    None,
)
_SPACE_LIKE = re.compile(r"[\s\u00a0\u1680\u2000-\u200a\u202f\u205f\u3000]+")


def clean_text(value: str | None) -> str | None:
    """HTML-unescape, drop tags, drop control/invisible characters, collapse whitespace.

    Returns None when nothing readable is left (None, blank, or markup only).
    """
    if value is None:
        return None
    text = html.unescape(value)
    text = _TAG.sub(" ", text)
    text = unicodedata.normalize("NFC", text).translate(_INVISIBLE)
    text = "".join(
        " "
        if unicodedata.category(ch) in {"Cc", "Cf", "Zl", "Zp"} and ch not in "\t"
        else ch
        for ch in text
    )
    text = _SPACE_LIKE.sub(" ", text).strip()
    return text or None
