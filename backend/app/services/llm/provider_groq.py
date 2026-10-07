import json
import time
import urllib.request

from app.services.llm.base import LLMResult


class GroqProvider:
    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        self.model = model or "llama-3.1-8b-instant"

    def complete(self, prompt: str, *, system: str | None = None) -> LLMResult:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        body = json.dumps(
            {
                "model": self.model,
                "messages": messages,
                "temperature": 0,
                "response_format": {"type": "json_object"},
            }
        ).encode()
        req = urllib.request.Request(
            "https://api.groq.com/openai/v1/chat/completions",
            data=body,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        start = time.monotonic()
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read())
        choice = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        return LLMResult(
            choice,
            usage.get("prompt_tokens"),
            usage.get("completion_tokens"),
            int((time.monotonic() - start) * 1000),
        )
