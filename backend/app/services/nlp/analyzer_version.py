"""`analyzer_version`: the key (with `content_hash`) under which NLP results are reused.

docs/ARCHITECTURE.md 5.1: model name + lexicon version + rule versions (clauses, relevance,
keywords, topics); changing any of them invalidates reuse. The aspect category preset is part
of it too, because the same text yields different `item_aspects` under different lexicons.
Sentiment settings that change labels (e.g. the neutral margin) are included through the
analyzer's optional `config_tag`.

Pure, stdlib only.
"""

from app.config.taxonomy import DEFAULT_CATEGORY, LEXICON_VERSION
from app.schemas.domain import Category
from app.services.nlp.clauses import CLAUSE_RULES_VERSION
from app.services.nlp.keywords import KEYWORD_RULES_VERSION
from app.services.nlp.relevance import RELEVANCE_RULES_VERSION
from app.services.nlp.sentiment import SentimentAnalyzer
from app.services.nlp.topics import TOPIC_RULES_VERSION

_SEPARATOR = "|"


def build_analyzer_version(
    model_name: str,
    category: Category | str = DEFAULT_CATEGORY,
    *,
    config_tag: str | None = None,
) -> str:
    """Compose the version string: model, then the rule versions, then the category, then the
    optional config tag, joined by `|`, e.g. `org/m|lex-1|clauses-1|relevance-1|keywords-1|`
    `topics-1|consumer_electronics|margin-0.15-len256`."""
    if not model_name or not model_name.strip():
        raise ValueError("model_name must not be blank")
    category_key = category.value if isinstance(category, Category) else category
    parts = [
        model_name,
        LEXICON_VERSION,
        CLAUSE_RULES_VERSION,
        RELEVANCE_RULES_VERSION,
        KEYWORD_RULES_VERSION,
        TOPIC_RULES_VERSION,
    ]
    parts.append(category_key)
    if config_tag:
        parts.append(config_tag)
    if any(_SEPARATOR in part for part in parts[1:]):
        raise ValueError(f"version parts must not contain {_SEPARATOR!r}")
    return _SEPARATOR.join(parts)


def analyzer_version_for(
    analyzer: SentimentAnalyzer, category: Category | str = DEFAULT_CATEGORY
) -> str:
    """`analyzer_version` of an analyzer; uses its `config_tag` attribute when it has one."""
    config_tag = getattr(analyzer, "config_tag", None)
    return build_analyzer_version(analyzer.model_name, category, config_tag=config_tag)
