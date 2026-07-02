"""LLM 后端抽象 — 本地模型 + API fallback."""

from .backend import LLMBackend, LLMResponse

__all__ = ["LLMBackend", "LLMResponse"]
