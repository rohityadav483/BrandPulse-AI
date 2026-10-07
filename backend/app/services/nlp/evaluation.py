"""Metrics and runner for the labeled sentiment evaluation set (Phase 4.3). Pure, no I/O
besides reading the dataset file and calling the analyzer.

Mirrors the production path in `item_analysis`: overall sentiment is scored on `title + snippet`
(`full_text`), aspects are found with the aspect lexicon, and each aspect clause is scored on
its own. All texts of one run go through a single `SentimentAnalyzer.analyze` call.

The analyzer is run once; `score(outcomes, margin=...)` can re-apply the neutral-margin rule
to the stored class probabilities, so a margin sweep needs one model pass, not one per margin.
The relabel uses the same function as `HFSentimentAnalyzer` (`hf_sentiment.to_result`); it is
exact except for float rounding at a margin boundary.
"""

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from app.config.taxonomy import DEFAULT_CATEGORY, get_lexicon
from app.schemas.domain import Category, Sentiment
from app.services.nlp.aspects import detect_aspects_in_text
from app.services.nlp.hf_sentiment import to_result
from app.services.nlp.item_analysis import ItemText, full_text
from app.services.nlp.sentiment import SentimentAnalyzer, SentimentResult

LABELS: tuple[str, ...] = ("negative", "neutral", "positive")
_CLASSES = (Sentiment.positive, Sentiment.neutral, Sentiment.negative)


@dataclass(frozen=True, slots=True)
class EvalItem:
    id: str
    brand: str
    title: str
    snippet: str
    label: str
    aspects: Mapping[str, str] = field(default_factory=dict)
    source: str = ""


@dataclass(frozen=True, slots=True)
class EvalDataset:
    name: str
    version: int
    category: str
    items: tuple[EvalItem, ...]


def load_dataset(path: str | Path) -> EvalDataset:
    """Read and validate the dataset file. Raises `ValueError` on any inconsistency."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    category = data.get("category", DEFAULT_CATEGORY)
    category_key = category.value if isinstance(category, Category) else category
    lexicon = get_lexicon(category_key)
    items: list[EvalItem] = []
    seen: set[str] = set()
    for raw in data["items"]:
        item_id = raw["id"]
        if item_id in seen:
            raise ValueError(f"duplicate id {item_id!r}")
        seen.add(item_id)
        if raw["label"] not in LABELS:
            raise ValueError(f"{item_id}: label must be one of {LABELS}, got {raw['label']!r}")
        if not str(raw.get("title", "")).strip():
            raise ValueError(f"{item_id}: title must not be blank")
        aspects = dict(raw.get("aspects") or {})
        for aspect, label in aspects.items():
            if aspect not in lexicon:
                raise ValueError(f"{item_id}: unknown aspect {aspect!r} for {category_key}")
            if label not in LABELS:
                raise ValueError(f"{item_id}: aspect {aspect!r} has invalid label {label!r}")
        items.append(
            EvalItem(
                id=item_id,
                brand=raw["brand"],
                title=raw["title"],
                snippet=raw.get("snippet") or "",
                label=raw["label"],
                aspects=aspects,
                source=raw.get("source", ""),
            )
        )
    if not items:
        raise ValueError("dataset has no items")
    return EvalDataset(
        data.get("name", ""), int(data.get("version", 1)), category_key, tuple(items)
    )


# ---- classification metrics ----


@dataclass(frozen=True, slots=True)
class ClassMetrics:
    precision: float
    recall: float
    f1: float
    support: int


@dataclass(frozen=True, slots=True)
class ClassificationReport:
    total: int
    accuracy: float
    macro_f1: float
    per_class: Mapping[str, ClassMetrics]
    # confusion[true_label][predicted_label] = count
    confusion: Mapping[str, Mapping[str, int]]


def _ratio(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0.0


def classification_report(
    expected: Sequence[str], predicted: Sequence[str], labels: Sequence[str] = LABELS
) -> ClassificationReport:
    """Accuracy, macro-F1 and per-class precision/recall/F1 plus the confusion matrix.

    Macro-F1 is the unweighted mean of the F1 of every label in `labels` (a label with no
    support and no predictions counts as F1 0.0). Precision, recall and F1 are 0.0 when their
    denominator is 0.
    """
    if len(expected) != len(predicted):
        raise ValueError("expected and predicted must have the same length")
    if not expected:
        raise ValueError("nothing to score")
    for value in (*expected, *predicted):
        if value not in labels:
            raise ValueError(f"unknown label {value!r}")
    confusion = {t: {p: 0 for p in labels} for t in labels}
    for true, pred in zip(expected, predicted, strict=True):
        confusion[true][pred] += 1
    per_class: dict[str, ClassMetrics] = {}
    for label in labels:
        tp = confusion[label][label]
        fp = sum(confusion[t][label] for t in labels) - tp
        fn = sum(confusion[label].values()) - tp
        precision = _ratio(tp, tp + fp)
        recall = _ratio(tp, tp + fn)
        f1 = _ratio(2 * precision * recall, precision + recall)
        per_class[label] = ClassMetrics(precision, recall, f1, tp + fn)
    correct = sum(confusion[label][label] for label in labels)
    return ClassificationReport(
        total=len(expected),
        accuracy=correct / len(expected),
        macro_f1=sum(m.f1 for m in per_class.values()) / len(labels),
        per_class=per_class,
        confusion=confusion,
    )


# ---- running the analyzer ----


@dataclass(frozen=True, slots=True)
class AspectOutcome:
    aspect: str
    clause: str
    expected: str | None  # None: detected but not annotated
    result: SentimentResult


@dataclass(frozen=True, slots=True)
class ItemOutcome:
    item: EvalItem
    result: SentimentResult
    aspects: tuple[AspectOutcome, ...]
    missed_aspects: tuple[str, ...]  # annotated but not detected by the lexicon


def run_analyzer(
    dataset: EvalDataset, analyzer: SentimentAnalyzer, *, category: str | None = None
) -> list[ItemOutcome]:
    """Score every item once, in one `analyze` call (as `analyze_items` does in production)."""
    category_key = category or dataset.category
    texts: list[str] = []
    plan: list[tuple[EvalItem, int, list[tuple[str, str, int]]]] = []
    for item in dataset.items:
        text = full_text(ItemText(item.title, item.snippet))
        overall_slot = len(texts)
        texts.append(text)
        slots: list[tuple[str, str, int]] = []
        for found in detect_aspects_in_text(text, category_key):
            slots.append((found.aspect, found.clause.text, len(texts)))
            texts.append(found.clause.text)
        plan.append((item, overall_slot, slots))
    results = analyzer.analyze(texts)
    if len(results) != len(texts):
        raise ValueError(f"analyzer returned {len(results)} results for {len(texts)} texts")
    outcomes: list[ItemOutcome] = []
    for item, overall_slot, slots in plan:
        detected = {aspect for aspect, _, _ in slots}
        outcomes.append(
            ItemOutcome(
                item=item,
                result=results[overall_slot],
                aspects=tuple(
                    AspectOutcome(aspect, clause, item.aspects.get(aspect), results[slot])
                    for aspect, clause, slot in slots
                ),
                missed_aspects=tuple(a for a in item.aspects if a not in detected),
            )
        )
    return outcomes


def relabel(result: SentimentResult, margin: float) -> SentimentResult:
    """Apply the neutral-margin rule to a result's class probabilities."""
    if not 0.0 <= margin < 1.0:
        raise ValueError("margin must be in [0, 1)")
    row = (result.positive_prob, result.neutral_prob, result.negative_prob)
    return to_result(row, _CLASSES, margin)


# ---- scoring ----


@dataclass(frozen=True, slots=True)
class Misclassified:
    id: str
    expected: str
    predicted: str
    positive_prob: float
    neutral_prob: float
    negative_prob: float
    text: str


@dataclass(frozen=True, slots=True)
class AspectDetection:
    expected: int  # annotated (item, aspect) pairs
    detected: int  # of those, found by the lexicon
    recall: float
    missed: tuple[str, ...]  # "item_id:aspect"
    unannotated_detected: int  # detected but not annotated (not an error: labels are partial)


@dataclass(frozen=True, slots=True)
class EvalReport:
    margin: float | None  # None: labels exactly as the analyzer produced them
    overall: ClassificationReport
    aspect_detection: AspectDetection
    aspect_sentiment: ClassificationReport | None  # annotated AND detected aspects only
    misclassified: tuple[Misclassified, ...]
    aspect_misclassified: tuple[str, ...]  # "item_id:aspect expected->predicted"


def score(outcomes: Sequence[ItemOutcome], *, margin: float | None = None) -> EvalReport:
    """Metrics for one run. With `margin`, labels are re-derived from the probabilities."""

    def label_of(result: SentimentResult) -> str:
        return (relabel(result, margin) if margin is not None else result).label.value

    expected = [o.item.label for o in outcomes]
    predicted = [label_of(o.result) for o in outcomes]
    wrong = tuple(
        Misclassified(
            o.item.id,
            exp,
            pred,
            o.result.positive_prob,
            o.result.neutral_prob,
            o.result.negative_prob,
            f"{o.item.title} | {o.item.snippet}",
        )
        for o, exp, pred in zip(outcomes, expected, predicted, strict=True)
        if exp != pred
    )
    annotated = sum(len(o.item.aspects) for o in outcomes)
    missed = tuple(f"{o.item.id}:{a}" for o in outcomes for a in o.missed_aspects)
    found = annotated - len(missed)
    extra = sum(1 for o in outcomes for a in o.aspects if a.expected is None)
    a_expected: list[str] = []
    a_predicted: list[str] = []
    a_wrong: list[str] = []
    for o in outcomes:
        for a in o.aspects:
            if a.expected is None:
                continue
            pred = label_of(a.result)
            a_expected.append(a.expected)
            a_predicted.append(pred)
            if pred != a.expected:
                a_wrong.append(f"{o.item.id}:{a.aspect} {a.expected}->{pred}")
    return EvalReport(
        margin=margin,
        overall=classification_report(expected, predicted),
        aspect_detection=AspectDetection(annotated, found, _ratio(found, annotated), missed, extra),
        aspect_sentiment=classification_report(a_expected, a_predicted) if a_expected else None,
        misclassified=wrong,
        aspect_misclassified=tuple(a_wrong),
    )


def sweep(
    outcomes: Sequence[ItemOutcome], margins: Sequence[float]
) -> list[tuple[float, EvalReport]]:
    """`score` for each margin, in the order given."""
    return [(margin, score(outcomes, margin=margin)) for margin in margins]
