from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class LLMResult:
    text: str
    tokens_in: int | None = None
    tokens_out: int | None = None
    latency_ms: int | None = None


class LLMProvider(Protocol):
    model: str

    def complete(self, prompt: str, *, system: str | None = None) -> LLMResult: ...
