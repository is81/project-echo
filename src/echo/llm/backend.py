"""LLM 后端：本地模型（Qwen2.5-7B）+ API fallback 机制.

策略:
  1. 优先使用本地模型（快速、离线可用）
  2. 当本地模型不可用或返回质量不足时，fallback 到云端 API
  3. 支持通过环境变量配置 API key
"""

import os
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class LLMResponse:
    """LLM 返回结果."""

    text: str
    model_used: str  # "local" | "api"
    tokens_used: int = 0
    finish_reason: str = "stop"


class LLMBackend:
    """LLM 后端管理器.

    Usage:
        backend = LLMBackend()
        response = await backend.generate("你好，你是谁？", system_prompt="...")
    """

    def __init__(
        self,
        local_model_path: Optional[str] = None,
        api_key: Optional[str] = None,
        api_base: Optional[str] = None,
    ):
        self.local_model_path = local_model_path or os.getenv(
            "ECHO_LOCAL_MODEL", "models/qwen2.5-7b-q4_k_m.gguf"
        )
        self.api_key = api_key or os.getenv("ECHO_API_KEY", "")
        self.api_base = api_base or os.getenv("ECHO_API_BASE", "https://api.openai.com/v1")

        self._local_model = None  # 延迟加载
        self._local_available: Optional[bool] = None

    # --- 本地模型 ---

    def _ensure_local_model(self) -> bool:
        """尝试加载本地模型. 返回是否成功."""
        if self._local_available is not None:
            return self._local_available

        model_path = self.local_model_path
        if not model_path or not os.path.exists(model_path):
            self._local_available = False
            return False

        try:
            from llama_cpp import Llama

            self._local_model = Llama(
                model_path=model_path,
                n_ctx=4096,
                n_threads=os.cpu_count() or 4,
                verbose=False,
            )
            self._local_available = True
            return True
        except ImportError:
            self._local_available = False
            return False
        except Exception:
            self._local_available = False
            return False

    def _generate_local(
        self,
        prompt: str,
        system_prompt: str = "",
        temperature: float = 0.8,
        max_tokens: int = 512,
    ) -> Optional[LLMResponse]:
        """使用本地模型生成."""
        if not self._ensure_local_model():
            return None

        full_prompt = f"{system_prompt}\n\n用户: {prompt}\n回响:"
        try:
            result = self._local_model(
                full_prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                top_p=0.9,
                stop=["用户:", "\n\n"],
            )
            text = result["choices"][0]["text"].strip()
            return LLMResponse(
                text=text,
                model_used="local",
                tokens_used=result.get("usage", {}).get("total_tokens", 0),
            )
        except Exception:
            return None

    # --- API 回退 ---

    def _generate_api(
        self,
        prompt: str,
        system_prompt: str = "",
        temperature: float = 0.8,
        max_tokens: int = 512,
    ) -> Optional[LLMResponse]:
        """使用云端 API 生成."""
        if not self.api_key:
            return None

        try:
            from openai import OpenAI

            client = OpenAI(api_key=self.api_key, base_url=self.api_base)
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            response = client.chat.completions.create(
                model=os.getenv("ECHO_API_MODEL", "gpt-4o-mini"),
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return LLMResponse(
                text=response.choices[0].message.content or "",
                model_used="api",
                tokens_used=response.usage.total_tokens if response.usage else 0,
                finish_reason=response.choices[0].finish_reason or "stop",
            )
        except Exception:
            return None

    # --- 公共接口 ---

    def generate(
        self,
        prompt: str,
        system_prompt: str = "",
        temperature: float = 0.8,
        max_tokens: int = 512,
    ) -> LLMResponse:
        """生成回应，自动 fallback.

        优先级: 本地模型 > API
        """
        # 尝试本地模型
        local_result = self._generate_local(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        if local_result:
            return local_result

        # Fallback 到 API
        api_result = self._generate_api(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        if api_result:
            return api_result

        # 完全不可用
        return LLMResponse(
            text="（我暂时无法回应——我的内部声音和外部的窗口都静默了。请检查模型或 API 配置。）",
            model_used="none",
        )

    @property
    def status(self) -> dict:
        """返回后端状态信息."""
        local_ok = self._ensure_local_model()
        return {
            "local_available": local_ok,
            "api_available": bool(self.api_key),
            "active_model": "local" if local_ok else ("api" if self.api_key else "none"),
        }
