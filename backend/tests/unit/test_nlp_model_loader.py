"""Lazy loader and the torch wiring, tested with fake `torch` / `transformers` modules.

The real libraries are never imported and no model is read (AGENTS.md rule 5). The real model
is exercised only by `tests/evals/test_real_sentiment_model.py` (marker `model`).
"""

import ast
import subprocess
import sys
import types
from pathlib import Path

import pytest

from app.services.nlp import hf_sentiment, model_loader
from app.services.nlp.model_loader import (
    ClassifierConfig,
    ModelUnavailableError,
    clear_classifier_cache,
    get_classifier,
    is_loaded,
    load_sequence_classifier,
)

NLP_DIR = Path(model_loader.__file__).parent
BACKEND = NLP_DIR.parents[2]


@pytest.fixture(autouse=True)
def _fresh_cache():
    clear_classifier_cache()
    yield
    clear_classifier_cache()


# ---- no heavy import at import time ----


def test_importing_loader_and_analyzer_does_not_import_torch_or_transformers():
    code = (
        "import sys\n"
        "import app.services.nlp.model_loader, app.services.nlp.hf_sentiment, "
        "app.services.nlp.item_analysis, app.services.nlp.analyzer_version\n"
        "bad = [m for m in ('torch', 'transformers', 'numpy', 'sqlalchemy') if m in sys.modules]\n"
        "assert not bad, bad\n"
    )
    subprocess.run([sys.executable, "-c", code], cwd=BACKEND, check=True)


@pytest.mark.parametrize(
    "module", ["model_loader", "hf_sentiment", "item_analysis", "analyzer_version"]
)
def test_no_module_level_import_of_a_model_library_or_the_database(module):
    tree = ast.parse((NLP_DIR / f"{module}.py").read_text(encoding="utf-8"))
    top_level: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            top_level.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            top_level.add(node.module)
    for name in top_level:
        assert not name.startswith(("torch", "transformers", "sqlalchemy", "numpy")), name
        if name.startswith("app."):
            assert name.startswith(("app.config.taxonomy", "app.schemas", "app.services.nlp")), name


# ---- singleton cache ----


def test_get_classifier_builds_once_per_config():
    built = []

    def factory(config):
        built.append(config)
        return object()

    config = ClassifierConfig("org/m")
    first = get_classifier(config, factory=factory)
    second = get_classifier(ClassifierConfig("org/m"), factory=factory)
    assert first is second and len(built) == 1
    assert is_loaded(config)


def test_different_configs_get_different_classifiers():
    a = get_classifier(ClassifierConfig("org/a"), factory=lambda c: object())
    b = get_classifier(ClassifierConfig("org/a", max_length=64), factory=lambda c: object())
    c = get_classifier(ClassifierConfig("org/a", cache_dir="/x"), factory=lambda c: object())
    assert len({id(a), id(b), id(c)}) == 3


def test_clear_cache_forces_a_reload():
    built = []
    config = ClassifierConfig("org/m")
    get_classifier(config, factory=lambda c: built.append(c) or object())
    clear_classifier_cache()
    assert not is_loaded(config)
    get_classifier(config, factory=lambda c: built.append(c) or object())
    assert len(built) == 2


def test_factory_failure_is_not_cached():
    config = ClassifierConfig("org/m")

    def boom(_):
        raise ModelUnavailableError("nope")

    with pytest.raises(ModelUnavailableError):
        get_classifier(config, factory=boom)
    assert not is_loaded(config)


# ---- missing optional libraries ----


def test_missing_torch_gives_a_clear_error(monkeypatch):
    monkeypatch.setitem(sys.modules, "torch", None)  # makes `import torch` raise ImportError
    with pytest.raises(ModelUnavailableError, match=r"\.\[nlp\]"):
        load_sequence_classifier(ClassifierConfig("org/m"))


# ---- torch wiring with fakes ----


class _Tensor:
    def __init__(self, rows):
        self.rows = rows

    def float(self):
        return self

    def tolist(self):
        return self.rows


class _FakeTorch(types.ModuleType):
    def __init__(self):
        super().__init__("torch")
        self.inference_active = False
        self.softmax_dims = []

    def inference_mode(self):
        outer = self

        class _Ctx:
            def __enter__(self):
                outer.inference_active = True

            def __exit__(self, *exc):
                outer.inference_active = False

        return _Ctx()

    def softmax(self, tensor, dim):
        self.softmax_dims.append(dim)
        out = []
        for row in tensor.rows:
            total = sum(row)
            out.append([v / total for v in row])
        return _Tensor(out)


def _install_fakes(monkeypatch, *, id2label=None, fail_with=None):
    torch = _FakeTorch()
    seen = {"tokenizer_calls": [], "model_calls": [], "from_pretrained": [], "moved": [], "eval": 0}

    class Tokenizer:
        @classmethod
        def from_pretrained(cls, model_id, **options):
            seen["from_pretrained"].append(("tokenizer", model_id, options))
            if fail_with:
                raise fail_with
            return cls()

        def __call__(self, texts, **options):
            seen["tokenizer_calls"].append((texts, options))
            return {"texts": texts}

    class Model:
        config = types.SimpleNamespace(
            id2label=id2label or {0: "negative", 1: "neutral", 2: "positive"}
        )

        @classmethod
        def from_pretrained(cls, model_id, **options):
            seen["from_pretrained"].append(("model", model_id, options))
            return cls()

        def to(self, device):
            seen["moved"].append(device)
            return self

        def eval(self):
            seen["eval"] += 1
            return self

        def __call__(self, texts):
            seen["model_calls"].append((list(texts), torch.inference_active))
            return types.SimpleNamespace(logits=_Tensor([[1.0, 1.0, 2.0] for _ in texts]))

    transformers = types.ModuleType("transformers")
    transformers.AutoTokenizer = Tokenizer
    transformers.AutoModelForSequenceClassification = Model
    monkeypatch.setitem(sys.modules, "torch", torch)
    monkeypatch.setitem(sys.modules, "transformers", transformers)
    return torch, seen


def test_load_builds_a_cpu_eval_classifier_with_the_configured_options(monkeypatch):
    _, seen = _install_fakes(monkeypatch)
    config = ClassifierConfig("org/m", cache_dir="/hf", local_files_only=True, max_length=64)
    classifier = load_sequence_classifier(config)
    options = {"cache_dir": "/hf", "local_files_only": True}
    assert seen["from_pretrained"] == [("tokenizer", "org/m", options), ("model", "org/m", options)]
    assert seen["moved"] == ["cpu"] and seen["eval"] == 1
    assert classifier.labels == ("negative", "neutral", "positive")


def test_predict_proba_tokenizes_with_truncation_and_runs_in_inference_mode(monkeypatch):
    torch, seen = _install_fakes(monkeypatch)
    classifier = load_sequence_classifier(ClassifierConfig("org/m", max_length=64))
    rows = classifier.predict_proba(["a", "b"])
    (texts, options) = seen["tokenizer_calls"][0]
    assert texts == ["a", "b"]
    assert options == {
        "padding": True,
        "truncation": True,
        "max_length": 64,
        "return_tensors": "pt",
    }
    assert seen["model_calls"] == [(["a", "b"], True)]  # ran inside inference_mode
    assert torch.softmax_dims == [-1]
    assert len(rows) == 2 and all(len(r) == 3 for r in rows)
    assert all(abs(sum(r) - 1.0) < 1e-9 for r in rows)
    assert rows[0][2] > rows[0][0]


def test_predict_proba_of_nothing_does_no_inference(monkeypatch):
    _, seen = _install_fakes(monkeypatch)
    classifier = load_sequence_classifier(ClassifierConfig("org/m"))
    assert classifier.predict_proba([]) == []
    assert seen["model_calls"] == [] and seen["tokenizer_calls"] == []


def test_hub_or_disk_errors_become_model_unavailable(monkeypatch):
    _install_fakes(monkeypatch, fail_with=OSError("no internet"))
    with pytest.raises(ModelUnavailableError, match="org/m.*no internet"):
        load_sequence_classifier(ClassifierConfig("org/m"))


def test_full_stack_through_the_analyzer_with_fake_libraries(monkeypatch):
    _install_fakes(monkeypatch)
    analyzer = hf_sentiment.HFSentimentAnalyzer("org/m", cache_dir="/hf", neutral_margin=0.0)
    assert not analyzer.is_loaded
    (result,) = analyzer.analyze(["anything"])
    assert analyzer.is_loaded
    assert result.label.value == "positive"  # fake logits favour column 2 (positive)
