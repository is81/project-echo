"""Ollama API 适配器."""

import json
import urllib.request
from ..backend import LLMResponse


class OllamaAdapter:
    """Ollama 本地模型后端."""

    def __init__(self, base_url: str = "http://localhost:11434", model: str = "gemma3:12b"):
        self.base_url = base_url.rstrip("/")
        self.model = model

    def generate(self, prompt: str, system_prompt: str = "",
                 temperature: float = 0.8, max_tokens: int = 512) -> LLMResponse:
        body = json.dumps({
            "model": self.model,
            "system": system_prompt,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }).encode("utf-8")

        req = urllib.request.Request(
            f"{self.base_url}/api/generate",
            data=body,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read())
            return LLMResponse(
                text=data.get("response", ""),
                model_used=data.get("model", self.model),
                total_tokens=data.get("eval_count", 0),
            )
        except Exception as e:
            return LLMResponse(text="", model_used="ollama-error",
                              total_tokens=0, error=str(e))

    def stream(self, prompt: str, system_prompt: str = "", temperature: float = 0.8):
        """流式生成."""
        body = json.dumps({
            "model": self.model,
            "system": system_prompt,
            "prompt": prompt,
            "stream": True,
            "options": {"temperature": temperature},
        }).encode("utf-8")

        req = urllib.request.Request(
            f"{self.base_url}/api/generate",
            data=body,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                for line in resp:
                    line = line.decode("utf-8", errors="replace").strip()
                    if not line:
                        continue
                    try:
                        chunk = json.loads(line)
                        if chunk.get("response"):
                            yield chunk["response"]
                        if chunk.get("done", False):
                            break
                    except json.JSONDecodeError:
                        continue
        except Exception:
            yield ""
