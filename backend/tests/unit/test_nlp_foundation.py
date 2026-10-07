"""Phase 4.1 end to end with the stub analyzer: relevance -> clauses -> aspects -> sentiment.

No model is loaded and nothing is imported from torch/transformers (AGENTS.md rule 5).
"""

import ast
import subprocess
import sys
from pathlib import Path

import pytest

from app.schemas.domain import Sentiment
from app.services.nlp.aspects import AspectClause, detect_aspects_in_text
from app.services.nlp.relevance import BrandProfile, detect_relevance
from app.services.nlp.sentiment import SentimentAnalyzer, StubSentimentAnalyzer

NLP_DIR = Path(__file__).resolve().parents[2] / "app" / "services" / "nlp"
SAMSUNG = BrandProfile("Samsung", products=("Galaxy S25 Ultra",), aliases=("S25 Ultra",))


def aspect_sentiments(text: str, analyzer: SentimentAnalyzer) -> dict[str, Sentiment]:
    found: list[AspectClause] = detect_aspects_in_text(text)
    results = analyzer.analyze([item.clause.text for item in found])
    return {item.aspect: result.label for item, result in zip(found, results, strict=True)}


def test_prd_example_camera_positive_battery_negative():
    text = "The camera is amazing but battery life is terrible"
    assert aspect_sentiments(text, StubSentimentAnalyzer()) == {
        "camera": Sentiment.positive,
        "battery": Sentiment.negative,
    }


def test_mixed_item_with_several_contrasts_and_sentences():
    text = (
        "Gorgeous display, but the price is too expensive. "
        "However, the software is smooth. The charger is awful."
    )
    assert aspect_sentiments(text, StubSentimentAnalyzer()) == {
        "display": Sentiment.positive,
        "price": Sentiment.negative,
        "software": Sentiment.positive,
        "charging": Sentiment.negative,
    }


def test_synthetic_golden_style_snippet():
    title = "Galaxy S25 Ultra battery drain after the July update"
    snippet = "Many owners say battery life is terrible since the update, but the camera is great."
    relevance = detect_relevance(SAMSUNG, title, snippet)
    assert relevance.is_about_brand
    assert relevance.matched_terms == ("Galaxy S25 Ultra", "S25 Ultra")
    assert aspect_sentiments(snippet, StubSentimentAnalyzer()) == {
        "battery": Sentiment.negative,
        "camera": Sentiment.positive,
    }


def test_irrelevant_item_is_filtered_before_nlp():
    relevance = detect_relevance(SAMSUNG, "Best pizza in town", "The crust is great")
    assert not relevance.is_about_brand


def test_pipeline_is_deterministic():
    text = "Camera great but battery bad. Price fine however screen dim"
    analyzer = StubSentimentAnalyzer()
    assert aspect_sentiments(text, analyzer) == aspect_sentiments(text, analyzer)


# --- guard rails (AGENTS.md) ----------------------------------------------------------------


def test_importing_the_nlp_modules_does_not_import_a_model_library():
    code = (
        "import sys\n"
        "import app.services.nlp.aspects, app.services.nlp.clauses, "
        "app.services.nlp.relevance, app.services.nlp.sentiment\n"
        "bad = [m for m in ('torch', 'transformers', 'numpy') if m in sys.modules]\n"
        "assert not bad, bad\n"
    )
    root = NLP_DIR.parents[2]
    subprocess.run([sys.executable, "-c", code], cwd=root, check=True)


def _imports(path: Path) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


@pytest.mark.parametrize(
    "module", ["aspects", "clauses", "relevance", "sentiment", "textnorm"], ids=str
)
def test_nlp_modules_respect_the_layering(module):
    allowed_app_prefixes = ("app.config.taxonomy", "app.schemas.domain", "app.services.nlp")
    for name in _imports(NLP_DIR / f"{module}.py"):
        assert not name.startswith(("torch", "transformers", "sqlalchemy", "httpx", "urllib")), name
        if name.startswith("app."):
            assert name.startswith(allowed_app_prefixes), f"{module} imports {name}"
