"""Anthropic Claude API 适配器."""

import json
import urllib.request
from ..backend import LLMResponse


class AnthropicAdapter:
    """Anthropic Messages API 后端."""

    def __init__(self, api_key: str = "", model: str = "claude-haiku-4-5-20251001"):
        self.api_key = api_key
        self.model = model
        self.base_url = "https://api.anthropic.com/v1"

    def generate(self, prompt: str, system_prompt: str = "",
                 temperature: float = 0.8, max_tokens: int = 512) -> LLMResponse:
        body = json.dumps({
            "model": self.model,
            "system": system_prompt,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }).encode("utf-8")

        req = urllib.request.Request(
            f"{self.base_url}/messages",
            data=body,
            headers={
                "Content-Type": "application/json",
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read())
            text = "".join(b.get("text", "") for b in data.get("content", []))
            return LLMResponse(text=text, model_used=self.model,
                              total_tokens=data.get("usage", {}).get("input_tokens", 0)
                              + data.get("usage", {}).get("output_tokens", 0))
        except Exception as e:
            return LLMResponse(text="", model_used="claude-error",
                              total_tokens=0, error=str(e))

    def stream(self, prompt: str, system_prompt: str = "", temperature: float = 0.8):
        result = self.generate(prompt, system_prompt, temperature)
        yield result.text
