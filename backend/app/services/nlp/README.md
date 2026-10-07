# services/nlp

Phase 4.1 (NLP foundation) plus Phase 4.2 (real local model, `analyzer_version`, item analysis). The 4.1 modules are pure, stdlib-only building blocks for the local NLP pipeline in `docs/ARCHITECTURE.md` section 5.1. No model, no torch, no network, no DB, no I/O. Services here never import other services, `api/`, repositories or DB models; they import only `app.config.taxonomy` and `app.schemas.domain`.

**Phase 4.2 added** (4.1 modules and behavior unchanged):

| Module | Role |
|---|---|
| `model_loader` | Lazy loader. `get_classifier(ClassifierConfig)` is a per-config singleton; `load_sequence_classifier` imports torch/transformers only when it runs, loads on CPU, `eval()`. `ModelUnavailableError` when libraries or files are missing. `clear_classifier_cache()` for tests |
| `hf_sentiment` | `HFSentimentAnalyzer` implements `SentimentAnalyzer`: lazy (loads on the first non-blank text), batches of 16, label mapping by model label (3-class and binary), probabilities renormalised, margin rule (top class must beat the runner-up by `neutral_margin`, default 0.15, untuned) else `neutral`, blank text = neutral without inference. `HFSentimentAnalyzer.from_settings(settings)` reads `sentiment_model` and `hf_home` |
| `analyzer_version` | `build_analyzer_version`, `analyzer_version_for(analyzer, category)`: `model\|lexicon\|clause rules\|relevance rules\|category[\|config tag]` |
| `item_analysis` | `analyze_items(items, profile, analyzer, category)` -> `ItemAnalysis` per item (relevance gate, overall sentiment on title + snippet, aspect clause sentiment), one `analyze` call per batch. Produces `app/schemas/nlp.py` types, which the repositories persist |

Persistence lives outside the services: `app/db/repositories/content_analysis.py` and `item_aspect.py` (services never import repositories). Still empty: `keywords.py`, `topics.py`.

Torch and transformers are optional (`pip install -e ".[nlp]"`); nothing imports them at import time and no unit test loads a model. The one real-model test is `tests/evals/test_real_sentiment_model.py` (marker `model`).

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
