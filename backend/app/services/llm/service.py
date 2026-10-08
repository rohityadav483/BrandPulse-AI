import json
import time

from app.services.llm.base import LLMProvider
from app.services.llm.limiter import LLMLimiter
from app.services.llm.structured import parse_json_object


def _status_for(exc: Exception) -> str:
    # HTTPError (urllib) carries `.code`; 429 is the provider's rate limit.
    return "rate_limited" if getattr(exc, "code", None) == 429 else "failed"


class LLMService:
    """Budgeted, concurrency-limited, audited access to one LLM provider."""

    def __init__(
        self,
        provider: LLMProvider | None,
        max_calls: int = 8,
        *,
        limiter: LLMLimiter | None = None,
        recorder=None,
    ):
        self.provider = provider
        self.max_calls = max_calls
        self.limiter = limiter
        self.recorder = recorder
        self.calls = 0

    def _record(self, **fields) -> None:
        if self.recorder is not None:
            self.recorder.record(model=getattr(self.provider, "model", "unknown"), **fields)

    def complete_json(self, prompt: str, *, system: str | None = None):
        if not self.provider or self.calls >= self.max_calls:
            raise RuntimeError("llm_unavailable")
        self.calls += 1
        started = time.monotonic()
        try:
            if self.limiter is not None:
                with self.limiter.slot():
                    started = time.monotonic()
                    result = self.provider.complete(prompt, system=system)
            else:
                result = self.provider.complete(prompt, system=system)
        except Exception as exc:
            self._record(
                status=_status_for(exc),
                latency_ms=int((time.monotonic() - started) * 1000),
                error=f"{type(exc).__name__}: {exc}",
            )
            raise
        fields = {
            "tokens_in": result.tokens_in,
            "tokens_out": result.tokens_out,
            "latency_ms": result.latency_ms
            if result.latency_ms is not None
            else int((time.monotonic() - started) * 1000),
        }
        try:
            parsed = parse_json_object(result.text)
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            self._record(status="invalid_json", error=f"{type(exc).__name__}: {exc}", **fields)
            raise
        self._record(status="ok", **fields)
        return parsed
