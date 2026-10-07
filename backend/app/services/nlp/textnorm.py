"""Comparison form shared by the NLP modules. Pure, stdlib only.

Kept local to `services/nlp` because services never import each other (AGENTS.md); it mirrors
the idea of `processing.normalizer.normalize_for_match` without depending on it.
"""

import re
import unicodedata

_NON_WORD = re.compile(r"[\W_]+", re.UNICODE)


def normalize_text(text: str | None) -> str:
    """NFKC, casefolded, punctuation/symbols/whitespace collapsed to single spaces.

    `"Wi-Fi"` -> `"wi fi"`, `"don't"` -> `"don t"`. Never shown to users; used to compare
    and to match lexicon terms on whole words.
    """
    if not text:
        return ""
    folded = unicodedata.normalize("NFKC", text).casefold()
    return _NON_WORD.sub(" ", folded).strip()
