"""LLM 后端适配器 —— 统一接口，多后端透明切换."""

from .openai import OpenAIAdapter
from .anthropic import AnthropicAdapter
from .ollama import OllamaAdapter

__all__ = ["OpenAIAdapter", "AnthropicAdapter", "OllamaAdapter"]
