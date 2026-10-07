"""Clause splitting: sentences first, then contrast words. Pure, stdlib only, no I/O.

"The camera is amazing but battery life is terrible" ->
`["The camera is amazing", "battery life is terrible"]`, so each aspect gets its own text to
score. The contrast word itself is dropped from the clauses (it carries no sentiment of its own
and would only confuse the analyzer).

Sentence boundaries: `.` `!` `?` followed by whitespace or the end, an ellipsis (`...`, `…`,
SerpApi snippets are full of them), `;` and line breaks. Dots inside numbers (`5.5`) or after
a few common abbreviations (`vs.`, `e.g.`) do not end a sentence.

Contrast words: `but`, `however`, `although`, `though` (also `even though`), `whereas`,
`nevertheless`, `nonetheless`, `on the other hand`; and `while` / `yet` only right after a comma
(`great screen, while the battery is poor`), because bare `while` ("while charging") and `yet`
("not yet") are usually not contrasts. Not split: `but also`, `all but`, `nothing but`,
`anything but`, `as though`. Known limitation: `however` is always a contrast
(`however good it is` is split wrongly); rare in review snippets.

Changing any rule changes results: bump `CLAUSE_RULES_VERSION` (part of the later
`analyzer_version`).
"""

import re
from dataclasses import dataclass

CLAUSE_RULES_VERSION = "clauses-1"

_BOUNDARY = re.compile(r"(?:[.!?]+|…|;)[\"')\]]*(?:\s+|$)|\s*\n+\s*")
_ABBREVIATIONS = frozenset(
    {"vs", "e.g", "i.e", "approx", "inc", "mr", "mrs", "ms", "dr", "st", "fig"}
)

_CONTRAST = re.compile(
    r"(?<!\w)(?:even\s+though|on\s+the\s+other\s+hand|but|however|although|though|whereas"
    r"|nevertheless|nonetheless|yet|while)(?!\w)",
    re.IGNORECASE,
)
_COMMA_ONLY = frozenset({"while", "yet"})
_NOT_AFTER = frozenset({"all", "nothing", "anything", "none", "as"})
_EDGE_PUNCT = " \t\r\n,;:-–—"
_WORD = re.compile(r"\w+")


@dataclass(frozen=True, slots=True)
class Clause:
    text: str  # original wording and case, edges trimmed, contrast word removed
    index: int  # position among all clauses of the text, from 0
    sentence_index: int  # position of the sentence it came from, from 0


def _sentences(text: str) -> list[str]:
    pieces: list[str] = []
    start = 0
    for match in _BOUNDARY.finditer(text):
        piece = text[start : match.start()]
        terminator = match.group().strip()
        if (
            terminator == "."
            and piece.split()
            and piece.split()[-1].casefold() in _ABBREVIATIONS
        ):
            continue
        pieces.append(piece)
        start = match.end()
    pieces.append(text[start:])
    return pieces


def _previous_word(text: str, end: int) -> str:
    words = _WORD.findall(text[:end])
    return words[-1].casefold() if words else ""


def _next_word(text: str, start: int) -> str:
    found = _WORD.search(text, start)
    return found.group().casefold() if found else ""


def _is_contrast(sentence: str, match: re.Match[str]) -> bool:
    word = " ".join(match.group().casefold().split())
    if word in _COMMA_ONLY:
        return sentence[: match.start()].rstrip().endswith(",")
    if word == "but":
        return (
            _next_word(sentence, match.end()) != "also"
            and _previous_word(sentence, match.start()) not in _NOT_AFTER
        )
    if word == "though":
        return _previous_word(sentence, match.start()) != "as"
    return True


def _split_contrast(sentence: str) -> list[str]:
    parts: list[str] = []
    start = 0
    for match in _CONTRAST.finditer(sentence):
        if _is_contrast(sentence, match):
            parts.append(sentence[start : match.start()])
            start = match.end()
    parts.append(sentence[start:])
    return parts


def split_clauses(text: str | None) -> list[Clause]:
    """Split text into clauses. None, blank or punctuation-only text gives an empty list."""
    if not text or not text.strip():
        return []
    clauses: list[Clause] = []
    sentence_index = 0
    for sentence in _sentences(text):
        produced = False
        for part in _split_contrast(sentence):
            cleaned = " ".join(part.split()).strip(_EDGE_PUNCT)
            if _WORD.search(cleaned):
                clauses.append(Clause(cleaned, len(clauses), sentence_index))
                produced = True
        if produced:
            sentence_index += 1
    return clauses
