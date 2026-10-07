from app.services.llm.base import LLMProvider
from app.services.llm.structured import parse_json_object


class LLMService:
    def __init__(self, provider: LLMProvider | None, max_calls: int = 8):
        self.provider = provider
        self.max_calls = max_calls
        self.calls = 0

    def complete_json(self, prompt: str, *, system: str | None = None):
        if not self.provider or self.calls >= self.max_calls:
            raise RuntimeError("llm_unavailable")
        self.calls += 1
        return parse_json_object(self.provider.complete(prompt, system=system).text)
