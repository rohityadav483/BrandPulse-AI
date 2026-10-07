"""Cheap NLP readiness checks for health/start gates; never download model files."""

from __future__ import annotations

import importlib.util

from app.services.nlp.model_loader import ClassifierConfig, is_loaded


def nlp_status(model_id: str, cache_dir: str | None = None) -> str:
    """Return ok/loading/unavailable without importing torch or touching the network."""
    if (
        importlib.util.find_spec("torch") is None
        or importlib.util.find_spec("transformers") is None
    ):
        return "unavailable"
    config = ClassifierConfig(model_id=model_id, cache_dir=cache_dir or None)
    return "ok" if is_loaded(config) else "loading"
