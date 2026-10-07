"""Eval metrics, dataset checks, margin relabel and `scripts/run_eval.py`. No model, no DB."""

import importlib.util
import json
import random
from collections import Counter
from pathlib import Path

import pytest

from app.schemas.domain import Sentiment
from app.services.nlp import evaluation
from app.services.nlp.evaluation import (
    EvalDataset,
    EvalItem,
    classification_report,
    load_dataset,
    relabel,
    run_analyzer,
    score,
    sweep,
)
from app.services.nlp.hf_sentiment import HFSentimentAnalyzer
from app.services.nlp.model_loader import clear_classifier_cache
from app.services.nlp.sentiment import SentimentResult, StubSentimentAnalyzer

BACKEND = Path(__file__).resolve().parents[2]
DATASET = BACKEND / "tests" / "fixtures" / "nlp" / "sentiment_eval_v1.json"
SCRIPT = BACKEND / "scripts" / "run_eval.py"


@pytest.fixture(autouse=True)
def _fresh_cache():
    clear_classifier_cache()
    yield
    clear_classifier_cache()


# ---- classification_report ----


def test_report_hand_computed_example():
    expected = ["positive", "positive", "negative", "neutral", "neutral", "neutral"]
    predicted = ["positive", "neutral", "negative", "neutral", "positive", "neutral"]
    report = classification_report(expected, predicted)
    assert report.total == 6
    assert report.accuracy == pytest.approx(4 / 6)
    assert report.confusion["positive"] == {"negative": 0, "neutral": 1, "positive": 1}
    assert report.confusion["neutral"] == {"negative": 0, "neutral": 2, "positive": 1}
    assert report.confusion["negative"] == {"negative": 1, "neutral": 0, "positive": 0}
    pos = report.per_class["positive"]  # tp 1, fp 1, fn 1
    assert (pos.precision, pos.recall, pos.f1, pos.support) == (0.5, 0.5, 0.5, 2)
    neu = report.per_class["neutral"]  # tp 2, fp 1, fn 1
    assert neu.precision == pytest.approx(2 / 3) and neu.recall == pytest.approx(2 / 3)
    neg = report.per_class["negative"]  # tp 1
    assert (neg.precision, neg.recall, neg.f1) == (1.0, 1.0, 1.0)
    assert report.macro_f1 == pytest.approx((0.5 + 2 / 3 + 1.0) / 3)


def test_perfect_and_worst_cases():
    labels = ["negative", "neutral", "positive"]
    perfect = classification_report(labels, labels)
    assert perfect.accuracy == 1.0 and perfect.macro_f1 == 1.0
    worst = classification_report(labels, ["positive", "negative", "neutral"])
    assert worst.accuracy == 0.0 and worst.macro_f1 == 0.0


def test_a_class_never_predicted_has_zero_precision_and_f1():
    report = classification_report(["negative", "neutral"], ["neutral", "neutral"])
    assert report.per_class["negative"].precision == 0.0
    assert report.per_class["negative"].f1 == 0.0
    assert report.per_class["positive"].support == 0
    assert report.macro_f1 == pytest.approx((0.0 + 2 / 3 + 0.0) / 3)


def test_report_input_checks():
    with pytest.raises(ValueError):
        classification_report(["positive"], [])
    with pytest.raises(ValueError):
        classification_report([], [])
    with pytest.raises(ValueError):
        classification_report(["positive"], ["great"])


# ---- the dataset ----


def test_dataset_size_labels_and_provenance():
    dataset = load_dataset(DATASET)
    assert 40 <= len(dataset.items) <= 60
    counts = Counter(item.label for item in dataset.items)
    assert set(counts) == {"negative", "neutral", "positive"}
    assert min(counts.values()) >= 10
    assert len({item.id for item in dataset.items}) == len(dataset.items)
    assert all(
        item.source == "handwritten" or item.source.startswith("fixture:") for item in dataset.items
    )
    assert sum(1 for item in dataset.items if item.source.startswith("fixture:")) >= 3
    assert sum(1 for item in dataset.items if item.aspects) >= 20


def test_dataset_contains_the_prd_camera_battery_case():
    dataset = load_dataset(DATASET)
    case = [i for i in dataset.items if i.aspects == {"camera": "positive", "battery": "negative"}]
    assert case


def test_fixture_sourced_items_match_the_serpapi_fixtures():
    dataset = load_dataset(DATASET)
    fixtures = BACKEND / "tests" / "fixtures" / "serpapi"
    for item in dataset.items:
        if not item.source.startswith("fixture:"):
            continue
        text = (fixtures / item.source.split(":", 1)[1]).read_text(encoding="utf-8")
        assert item.title in text and item.snippet in text, item.id


def _write(tmp_path, items, **extra):
    path = tmp_path / "d.json"
    path.write_text(json.dumps({"name": "t", "version": 1, "items": items, **extra}))
    return path


def _item(**overrides):
    base = {
        "id": "a",
        "brand": "Samsung",
        "title": "Samsung phone",
        "snippet": "ok",
        "label": "neutral",
    }
    return {**base, **overrides}


@pytest.mark.parametrize(
    "bad",
    [
        _item(label="great"),
        _item(title="  "),
        _item(aspects={"nonsense": "positive"}),
        _item(aspects={"battery": "great"}),
    ],
)
def test_load_dataset_rejects_inconsistent_items(tmp_path, bad):
    with pytest.raises(ValueError):
        load_dataset(_write(tmp_path, [bad]))


def test_load_dataset_rejects_duplicate_ids_and_empty(tmp_path):
    with pytest.raises(ValueError, match="duplicate"):
        load_dataset(_write(tmp_path, [_item(), _item()]))
    with pytest.raises(ValueError, match="no items"):
        load_dataset(_write(tmp_path, []))


# ---- run_analyzer / score ----


def _dataset(*items):
    return EvalDataset("t", 1, "consumer_electronics", tuple(items))


def test_run_analyzer_uses_one_call_and_the_production_text_and_clauses():
    class Counting(StubSentimentAnalyzer):
        def __init__(self):
            self.calls = []

        def analyze(self, texts):
            self.calls.append(list(texts))
            return super().analyze(texts)

    item = EvalItem(
        "x",
        "Samsung",
        "S25 Ultra",
        "The camera is amazing but battery life is terrible",
        "negative",
        {"camera": "positive", "battery": "negative", "audio": "positive"},
    )
    analyzer = Counting()
    (outcome,) = run_analyzer(_dataset(item), analyzer)
    assert len(analyzer.calls) == 1
    assert analyzer.calls[0][0] == "S25 Ultra. The camera is amazing but battery life is terrible"
    assert [a.aspect for a in outcome.aspects] == ["camera", "battery"]
    assert [a.clause for a in outcome.aspects] == [
        "The camera is amazing",
        "battery life is terrible",
    ]
    assert outcome.missed_aspects == ("audio",)
    assert [a.result.label for a in outcome.aspects] == [Sentiment.positive, Sentiment.negative]


def test_score_aspect_detection_and_sentiment_counts():
    items = (
        EvalItem(
            "a",
            "S",
            "S25",
            "The camera is amazing but battery life is terrible",
            "neutral",
            {"camera": "positive", "battery": "negative", "audio": "positive"},
        ),
        EvalItem("b", "S", "S25", "Great display, awful price", "neutral", {"display": "positive"}),
    )
    report = score(run_analyzer(_dataset(*items), StubSentimentAnalyzer()))
    detection = report.aspect_detection
    assert (detection.expected, detection.detected) == (4, 3)
    assert detection.recall == pytest.approx(3 / 4)
    assert detection.missed == ("a:audio",)
    assert detection.unannotated_detected == 1  # price in b
    assert report.aspect_sentiment.total == 3
    # camera and battery clauses split on "but" and are right; "Great display, awful price" is
    # one clause (no split on a comma), so the stub scores it neutral, not positive.
    assert report.aspect_sentiment.accuracy == pytest.approx(2 / 3)
    assert report.aspect_misclassified == ("b:display positive->neutral",)


def test_score_without_annotated_aspects_has_no_aspect_sentiment():
    report = score(
        run_analyzer(
            _dataset(EvalItem("a", "S", "S25", "great", "positive")), StubSentimentAnalyzer()
        )
    )
    assert report.aspect_sentiment is None
    assert report.aspect_detection.expected == 0 and report.aspect_detection.recall == 0.0


def test_misclassified_items_are_listed_with_probabilities():
    items = (EvalItem("a", "S", "S25 great", "", "negative"),)
    report = score(run_analyzer(_dataset(*items), StubSentimentAnalyzer()))
    (wrong,) = report.misclassified
    assert (wrong.id, wrong.expected, wrong.predicted) == ("a", "negative", "positive")


# ---- margin relabel / sweep ----


class _Probs:
    labels = ("negative", "neutral", "positive")

    def __init__(self, rows):
        self._rows = rows

    def predict_proba(self, texts):
        return [self._rows[t] for t in texts]


def _random_rows(count, seed=7):
    rng = random.Random(seed)
    rows = {}
    for n in range(count):
        raw = [rng.random() ** 2 for _ in range(3)]
        total = sum(raw)
        rows[f"text {n}"] = [value / total for value in raw]
    return rows


@pytest.mark.parametrize("margin", [0.0, 0.05, 0.15, 0.3, 0.6])
def test_relabel_equals_an_analyzer_built_with_that_margin(margin):
    rows = _random_rows(200)
    texts = list(rows)

    def build(model_id, neutral_margin):
        return HFSentimentAnalyzer(
            model_id, neutral_margin=neutral_margin, classifier_factory=lambda _c: _Probs(rows)
        )

    raw = build("org/raw", 0.0).analyze(texts)
    direct = build(f"org/m{margin}", margin).analyze(texts)
    assert [relabel(r, margin).label for r in raw] == [r.label for r in direct]


def test_relabel_keeps_probabilities_and_validates_margin():
    result = SentimentResult(Sentiment.positive, 0.5, 0.3, 0.2)
    again = relabel(result, 0.5)
    assert again.label is Sentiment.neutral
    assert (again.positive_prob, again.neutral_prob, again.negative_prob) == pytest.approx(
        (0.5, 0.3, 0.2)
    )
    for bad in (-0.1, 1.0):
        with pytest.raises(ValueError):
            relabel(result, bad)


def test_higher_margin_never_removes_neutral_predictions():
    rows = _random_rows(60)
    analyzer = HFSentimentAnalyzer(
        "org/sweep", neutral_margin=0.0, classifier_factory=lambda _c: _Probs(rows)
    )
    results = analyzer.analyze(list(rows))
    neutral_counts = [
        sum(1 for r in results if relabel(r, margin).label is Sentiment.neutral)
        for margin in (0.0, 0.1, 0.2, 0.4, 0.8)
    ]
    assert neutral_counts == sorted(neutral_counts)


def test_sweep_returns_one_report_per_margin_in_order():
    outcomes = run_analyzer(load_dataset(DATASET), StubSentimentAnalyzer())
    swept = sweep(outcomes, [0.0, 0.3])
    assert [m for m, _ in swept] == [0.0, 0.3]
    assert all(report.overall.total == len(outcomes) for _, report in swept)


# ---- the script ----


def load_script():
    spec = importlib.util.spec_from_file_location("run_eval", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_script_runs_with_the_stub_and_writes_json(tmp_path, capsys):
    out = tmp_path / "eval.json"
    assert load_script().main(["--json-out", str(out), "--show-errors"]) == 0
    printed = capsys.readouterr().out
    for needle in ("accuracy=", "macro_f1=", "confusion matrix", "aspect detection: recall="):
        assert needle in printed
    payload = json.loads(out.read_text())
    assert payload["analyzer"] == "stub" and payload["dataset"]["n"] == len(
        load_dataset(DATASET).items
    )
    overall = payload["report"]["overall"]
    assert set(overall["per_class"]) == {"negative", "neutral", "positive"}
    assert sum(sum(row.values()) for row in overall["confusion"].values()) == overall["total"]


def test_script_numbers_match_the_library(tmp_path):
    out = tmp_path / "eval.json"
    load_script().main(["--json-out", str(out)])
    expected = score(run_analyzer(load_dataset(DATASET), StubSentimentAnalyzer()))
    reported = json.loads(out.read_text())["report"]["overall"]
    assert reported["accuracy"] == expected.overall.accuracy
    assert reported["macro_f1"] == expected.overall.macro_f1


def test_script_sweep_needs_the_real_model(capsys):
    assert load_script().main(["--sweep"]) == 2
    assert "--analyzer hf" in capsys.readouterr().out


def test_script_reports_an_unavailable_real_model_without_inventing_numbers(monkeypatch, capsys):
    import sys

    monkeypatch.setitem(sys.modules, "torch", None)  # `import torch` raises ImportError
    assert load_script().main(["--analyzer", "hf", "--local-files-only"]) == 2
    printed = capsys.readouterr().out
    assert "REAL MODEL NOT AVAILABLE" in printed
    assert "accuracy" not in printed


def test_script_enforce_fails_below_thresholds(capsys):
    assert load_script().main(["--enforce", "--min-accuracy", "1.01"]) == 1
    assert "BELOW THRESHOLD" in capsys.readouterr().out
    assert load_script().main(["--enforce", "--min-accuracy", "0", "--min-macro-f1", "0"]) == 0


def test_script_rejects_a_bad_margin(capsys):
    assert load_script().main(["--neutral-margin", "1.5"]) == 2


def test_evaluation_module_imports_no_model_library():
    import ast

    tree = ast.parse(Path(evaluation.__file__).read_text(encoding="utf-8"))
    roots = {
        (node.module or "").split(".")[0]
        if isinstance(node, ast.ImportFrom)
        else alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import | ast.ImportFrom)
        for alias in (node.names if isinstance(node, ast.Import) else [None])
    }
    assert not roots & {"torch", "transformers", "sqlalchemy"}
