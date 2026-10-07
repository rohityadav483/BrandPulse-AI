"""Lazy loader for the local Hugging Face sequence-classification model (CPU only).

Importing this module never imports torch or transformers and never touches the disk or the
network. They are imported inside `load_sequence_classifier`, which runs on the first real
inference only. `get_classifier` keeps one loaded classifier per configuration (lazy
singleton), so the model is read once per process.

Not for unit tests (AGENTS.md rule 5): tests inject a fake `SequenceClassifier` or a fake
`factory`. Torch and transformers are optional (`pip install -e ".[nlp]"`), not core
dependencies.
"""

import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

DEFAULT_MAX_LENGTH = 256


class ModelUnavailableError(RuntimeError):
    """The model or its libraries cannot be loaded (not installed, not downloaded, offline)."""


@runtime_checkable
class SequenceClassifier(Protocol):
    """A loaded text classifier.

    `labels[i]` is the model's own name for output column `i` (e.g. `negative`, `LABEL_2`);
    `predict_proba` returns one row of class probabilities per text, in the same order, each
    row as long as `labels`. Mapping labels to sentiments is `hf_sentiment`'s job.
    """

    labels: tuple[str, ...]

    def predict_proba(self, texts: Sequence[str]) -> list[list[float]]: ...


@dataclass(frozen=True, slots=True)
class ClassifierConfig:
    model_id: str
    cache_dir: str | None = None
    local_files_only: bool = False
    max_length: int = DEFAULT_MAX_LENGTH


ClassifierFactory = Callable[[ClassifierConfig], SequenceClassifier]


class _TorchClassifier:
    def __init__(self, tokenizer, model, torch_module, max_length: int) -> None:
        self._tokenizer = tokenizer
        self._model = model
        self._torch = torch_module
        self._max_length = max_length
        id2label = model.config.id2label
        self.labels: tuple[str, ...] = tuple(str(id2label[i]) for i in range(len(id2label)))

    def predict_proba(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        encoded = self._tokenizer(
            list(texts),
            padding=True,
            truncation=True,
            max_length=self._max_length,
            return_tensors="pt",
        )
        with self._torch.inference_mode():
            logits = self._model(**encoded).logits
            probabilities = self._torch.softmax(logits.float(), dim=-1)
        return [[float(p) for p in row] for row in probabilities.tolist()]


def load_sequence_classifier(config: ClassifierConfig) -> SequenceClassifier:
    """Load tokenizer and model on CPU. Slow (disk, possibly a first-time download)."""
    try:
        import torch
        from transformers import (
            AutoModelForSequenceClassification,
            AutoTokenizer,
        )
    except (ImportError, OSError) as exc:
        # OSError: a half-installed torch (missing native libraries) fails on import with it.
        raise ModelUnavailableError(
            "torch and transformers are required for the local sentiment model and could not "
            f"be imported ({type(exc).__name__}: {exc}); "
            'install them with `pip install -e ".[nlp]"`'
        ) from exc
    try:
        options = {"cache_dir": config.cache_dir, "local_files_only": config.local_files_only}
        tokenizer = AutoTokenizer.from_pretrained(config.model_id, **options)
        model = AutoModelForSequenceClassification.from_pretrained(config.model_id, **options)
    except Exception as exc:  # hub, disk, network and format errors all mean "unavailable"
        raise ModelUnavailableError(
            f"could not load sentiment model {config.model_id!r}: {exc}"
        ) from exc
    model.to("cpu")
    model.eval()
    return _TorchClassifier(tokenizer, model, torch, config.max_length)


_cache: dict[ClassifierConfig, SequenceClassifier] = {}
_lock = threading.Lock()


def get_classifier(
    config: ClassifierConfig, *, factory: ClassifierFactory = load_sequence_classifier
) -> SequenceClassifier:
    """The classifier for `config`, loaded on first use and then reused (lazy singleton).

    A failed load is not cached, so a later call can retry (e.g. after a download).
    """
    with _lock:
        classifier = _cache.get(config)
        if classifier is None:
            classifier = factory(config)
            _cache[config] = classifier
        return classifier


def is_loaded(config: ClassifierConfig) -> bool:
    with _lock:
        return config in _cache


def clear_classifier_cache() -> None:
    """Forget every loaded classifier (tests, or to free memory)."""
    with _lock:
        _cache.clear()
