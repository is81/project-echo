"""LLM 后端：本地 llama-server + 云端 API fallback.

策略:
  1. 默认连接本地 llama-server (OpenAI 兼容 /v1/chat/completions)
  2. 如果本地服务不可用，fallback 到云端 API
  3. llama-server 不需要 API key，云端 API 需要

环境变量:
  ECHO_LLAMA_SERVER  - llama-server 地址 (默认 http://127.0.0.1:8080/v1)
  ECHO_API_KEY       - 云端 API key (fallback 用)
  ECHO_API_BASE      - 云端 API 地址 (默认 https://api.openai.com/v1)
  ECHO_API_MODEL     - 云端模型名 (默认 gpt-4o-mini)
"""

import os
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Optional


@dataclass
class LLMResponse:
    """LLM 返回结果."""

    text: str
    model_used: str  # "local" | "api" | "none"
    tokens_used: int = 0
    finish_reason: str = "stop"


class LLMBackend:
    """LLM 后端管理器 — 本地 llama-server 优先，云端 API 兜底."""

    def __init__(
        self,
        llama_server_url: Optional[str] = None,
        api_key: Optional[str] = None,
        api_base: Optional[str] = None,
    ):
        # 本地 llama-server 配置
        self.llama_server_url = llama_server_url or os.getenv(
            "ECHO_LLAMA_SERVER", "http://127.0.0.1:8080/v1"
        )
        # 云端 API 配置
        self.api_key = api_key or os.getenv("ECHO_API_KEY", "")
        self.api_base = api_base or os.getenv(
            "ECHO_API_BASE", "https://api.openai.com/v1"
        )
        self.api_model = os.getenv("ECHO_API_MODEL", "gpt-4o-mini")

    # --- 通用 OpenAI 兼容 API 调用 ---

    def _call_openai_compatible(
        self,
        prompt: str,
        system_prompt: str,
        temperature: float,
        max_tokens: int,
        base_url: str,
        api_key: str = "",
        model: str = "",
    ) -> Optional[LLMResponse]:
        """向 OpenAI 兼容端点发送请求（非流式）."""
        try:
            from openai import OpenAI

            client = OpenAI(
                api_key=api_key or "not-needed",
                base_url=base_url,
            )

            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            response = client.chat.completions.create(
                model=model or "local-model",
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )

            return LLMResponse(
                text=response.choices[0].message.content or "",
                model_used=model or "local",
                tokens_used=response.usage.total_tokens if response.usage else 0,
                finish_reason=response.choices[0].finish_reason or "stop",
            )
        except Exception:
            return None

    def _stream_openai_compatible(
        self,
        prompt: str,
        system_prompt: str,
        temperature: float,
        max_tokens: int,
        base_url: str,
        api_key: str = "",
        model: str = "",
    ) -> Optional[Iterator[str]]:
        """向 OpenAI 兼容端点发送流式请求，返回 token 迭代器.

        Gemma 4 会输出 reasoning_content（内部推理），我们跳过它，
        只 yield 实际 content。如果 enable_thinking 设为 false 则禁用推理。
        """
        try:
            from openai import OpenAI

            client = OpenAI(
                api_key=api_key or "not-needed",
                base_url=base_url,
                timeout=120.0,
            )

            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            stream = client.chat.completions.create(
                model=model or "local-model",
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True,
                extra_body={"enable_thinking": False},  # 禁用 Gemma 4 内部推理
            )

            def token_iter():
                for chunk in stream:
                    if not chunk.choices:
                        continue
                    delta = chunk.choices[0].delta
                    if not delta:
                        continue
                    # 优先取 content（跳过 reasoning_content）
                    if delta.content:
                        yield delta.content

            return token_iter()
        except Exception:
            return None

    # --- 本地 llama-server ---

    def _check_llama_server(self) -> bool:
        """快速检查本地 llama-server 是否在运行."""
        try:
            from openai import OpenAI

            client = OpenAI(api_key="not-needed", base_url=self.llama_server_url)
            client.models.list()
            return True
        except Exception:
            return False

    def _generate_local(
        self,
        prompt: str,
        system_prompt: str = "",
        temperature: float = 0.8,
        max_tokens: int = 256,
    ) -> Optional[LLMResponse]:
        """通过本地 llama-server 生成（非流式）."""
        return self._call_openai_compatible(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            base_url=self.llama_server_url,
            api_key="",
            model="local-model",
        )

    def _stream_local(
        self,
        prompt: str,
        system_prompt: str = "",
        temperature: float = 0.8,
        max_tokens: int = 256,
    ) -> Optional[Iterator[str]]:
        """通过本地 llama-server 流式生成."""
        return self._stream_openai_compatible(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            base_url=self.llama_server_url,
            api_key="",
            model="local-model",
        )

    # --- 云端 API ---

    def _generate_api(
        self,
        prompt: str,
        system_prompt: str = "",
        temperature: float = 0.8,
        max_tokens: int = 256,
    ) -> Optional[LLMResponse]:
        """通过云端 API 生成（非流式）."""
        if not self.api_key:
            return None
        return self._call_openai_compatible(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            base_url=self.api_base,
            api_key=self.api_key,
            model=self.api_model,
        )

    # --- 公共接口 ---

    def generate(
        self,
        prompt: str,
        system_prompt: str = "",
        temperature: float = 0.8,
        max_tokens: int = 256,
    ) -> LLMResponse:
        """生成回应（非流式）。优先级: 本地 llama-server > 云端 API."""
        local_result = self._generate_local(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        if local_result:
            return local_result

        api_result = self._generate_api(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        if api_result:
            return api_result

        return LLMResponse(
            text=(
                "（我暂时无法回应。请确认：\n"
                "1. llama-server 已启动 → llama-server -m <模型路径> --port 8080\n"
                "2. 或设置 ECHO_API_KEY 使用云端 API）"
            ),
            model_used="none",
        )

    def stream(
        self,
        prompt: str,
        system_prompt: str = "",
        temperature: float = 0.8,
        max_tokens: int = 256,
    ) -> tuple[Iterator[str], str]:
        """流式生成回应。返回 (token迭代器, 模型名).

        优先级: 本地 llama-server > 云端 API.
        如果两者都不可用，返回一个只产出错误消息的迭代器.
        """
        # 尝试本地
        local_stream = self._stream_local(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        if local_stream:
            return local_stream, "local"

        # Fallback 到非流式 API（保持简单）
        api_result = self._generate_api(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        if api_result:

            def single_iter():
                yield api_result.text

            return single_iter(), "api"

        # 完全不可用
        def error_iter():
            yield "（我暂时无法回应。请确认 llama-server 已启动或 ECHO_API_KEY 已设置。）"

        return error_iter(), "none"

    @property
    def status(self) -> dict:
        """返回后端状态信息."""
        local_ok = self._check_llama_server()
        return {
            "llama_server_available": local_ok,
            "llama_server_url": self.llama_server_url,
            "api_available": bool(self.api_key),
            "active_model": "llama-server" if local_ok else ("api" if self.api_key else "none"),
        }
