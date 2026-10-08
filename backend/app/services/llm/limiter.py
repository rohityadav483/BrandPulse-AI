"""Process-wide cap on simultaneous LLM provider calls (`Settings.llm_max_concurrency`)."""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager


class LLMLimiter:
    """Counting gate. The limit is re-read on every acquire, so a changed setting applies."""

    def __init__(self, max_concurrency: int = 1, max_calls: int = 8):
        self.max_concurrency = max(1, max_concurrency)
        self.max_calls = max_calls
        self._cond = threading.Condition()
        self._active = 0
        self.peak = 0

    @property
    def active(self) -> int:
        with self._cond:
            return self._active

    @contextmanager
    def slot(self) -> Iterator[None]:
        with self._cond:
            while self._active >= self.max_concurrency:
                self._cond.wait()
            self._active += 1
            self.peak = max(self.peak, self._active)
        try:
            yield
        finally:
            with self._cond:
                self._active -= 1
                self._cond.notify_all()


_shared = LLMLimiter()


def shared_limiter(max_concurrency: int) -> LLMLimiter:
    """The single limiter every investigation shares; its limit follows the setting."""
    with _shared._cond:
        _shared.max_concurrency = max(1, max_concurrency)
        _shared._cond.notify_all()
    return _shared
