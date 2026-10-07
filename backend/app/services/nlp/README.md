# services/nlp

Phase 4.1 (NLP foundation). Pure, stdlib-only building blocks for the local NLP pipeline in `docs/ARCHITECTURE.md` section 5.1. No model, no torch, no network, no DB, no I/O. Services here never import other services, `api/`, repositories or DB models; they import only `app.config.taxonomy` and `app.schemas.domain`.

**Not in 4.1:** the real BERT/RoBERTa implementation, `model_loader`, `keywords`, `topics`, `content_analysis` / `item_aspects` tables (migration `0005`), repositories, pipeline stage, API changes. `model_loader.py`, `keywords.py` and `topics.py` are still empty files.

## Inputs and outputs

| Module | In | Out |
|---|---|---|
| `relevance.detect_relevance(profile, title, snippet)` | `BrandProfile(brand, products, aliases)` + item title and snippet | `RelevanceResult(is_about_brand, matched_terms, in_title, in_snippet)` |
| `clauses.split_clauses(text)` | text or None | `list[Clause(text, index, sentence_index)]` |
| `aspects.detect_aspects(clauses, category)` / `detect_aspects_in_text(text, category)` | clauses (or text), category preset | `list[AspectClause(aspect, clause, matched_terms)]`, at most one per aspect |
| `aspects.terms_in_text(text, category)` | one text | `{aspect: matched lexicon terms}` |
| `sentiment.SentimentAnalyzer` (protocol) | `analyze(texts)` + `model_name` | one `SentimentResult(label, positive_prob, neutral_prob, negative_prob)` per text, same order; `.score` = positive - negative |
| `sentiment.StubSentimentAnalyzer` | same | deterministic keyword-count results for tests |
| `config/taxonomy.get_lexicon(category)` | `Category` or its string value | read-only `{aspect: terms}`; unknown category raises `ValueError` |

Value types are frozen dataclasses (stdlib), not Pydantic: nothing here crosses an API or DB boundary yet. Phase 4.2 maps them to the persisted shapes.

## Rules

- **Relevance:** brand name, product names and aliases, matched as whole words in title or snippet, ignoring case, punctuation and spacing (`Samsung's`, `galaxy-s25 ULTRA` match). Nothing is derived: an alias such as `S25 Ultra` must be configured. `matched_terms` use the configured spelling, in brand, products, aliases order; an alias that sits inside a longer product name matches too. Blank and duplicate terms are ignored; a brand with no letter or digit raises `ValueError`. Ambiguous brand names (the fruit) are not handled.
- **Clauses:** sentences end at `. ! ?` followed by whitespace, an ellipsis, `;` or a line break (not inside numbers, not after `vs.`, `e.g.` etc.). Then each sentence is split at contrast words and the contrast word is dropped: `but`, `however`, `although`, `though`, `even though`, `whereas`, `nevertheless`, `nonetheless`, `on the other hand`; `while` and `yet` only right after a comma. Not split: `but also`, `all/nothing/anything but`, `as though`. Original wording and case are kept.
- **Aspects:** lexicons live in `app/config/taxonomy.py` (`consumer_electronics`: battery, charging, camera, display, performance, price, design, software, customer_support, audio, connectivity; `generic`: quality, price, design, customer_support, reliability, usability, delivery). Whole-word match after normalisation, optional plural `s`/`es`. One entry per aspect (`item_aspects` PK is `(content_id, aspect)`): the clause with the most distinct matched terms, ties to the earliest. One clause can carry several aspects. Deliberately absent: bare `update`, `slow`, `fast`, `support`, `signal`, `look`, `build`, `heavy` (too ambiguous alone); recall on them is a known limitation to measure on real snippets.
- **Sentiment:** `SentimentResult` probabilities must lie in [0, 1] and sum to 1. The stub counts positive and negative words, flips a word when a negator (`not`, `never`, `isn't`...) is within two words before it, and is a test double, not a quality baseline. The neutral-margin rule belongs to the real model implementation (4.2+).

## Versions (for the later `analyzer_version`)

`taxonomy.LEXICON_VERSION = "lex-1"`, `clauses.CLAUSE_RULES_VERSION = "clauses-1"`, `relevance.RELEVANCE_RULES_VERSION = "relevance-1"`, stub model name `stub-lexicon-v1`. Change the matching constant whenever a lexicon term or rule changes. Composing them into `analyzer_version` is Phase 4.2.

## Failure behavior

Text functions never raise on odd input: None, blank or wordless text gives empty results / neutral. `ValueError` for an unknown category or a brand without letters/digits, `TypeError` for a bare string where a sequence is required (`BrandProfile` terms, `analyze`), `ValueError` for invalid probabilities.
