"""OpenAI API 适配器."""

import json
import urllib.request
from typing import Optional

from ..backend import LLMBackend, LLMResponse


class OpenAIAdapter:
    """OpenAI-compatible API 后端."""

    def __init__(self, api_key: str = "", base_url: str = "https://api.openai.com/v1",
                 model: str = "gpt-4o-mini"):
        self.api_key = api_key or "sk-placeholder"
        self.base_url = base_url.rstrip("/")
        self.model = model

    def generate(self, prompt: str, system_prompt: str = "",
                 temperature: float = 0.8, max_tokens: int = 512) -> LLMResponse:
        """非流式生成."""
        body = json.dumps({
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }).encode("utf-8")

        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read())
            text = data["choices"][0]["message"]["content"]
            return LLMResponse(text=text, model_used=self.model,
                              total_tokens=data.get("usage", {}).get("total_tokens", 0))
        except Exception as e:
            return LLMResponse(text="", model_used="openai-error",
                              total_tokens=0, error=str(e))

    def stream(self, prompt: str, system_prompt: str = "",
               temperature: float = 0.8):
        """流式生成 (简化版 — 返回完整文本)."""
        # 流式传输需要 sseclient，这里简化为非流式
        result = self.generate(prompt, system_prompt, temperature)
        yield result.text
