"""工具注册表.

每个工具是一个 Python 函数 + JSON Schema 描述.
注册表负责: 注册工具、生成 OpenAI 兼容的 tools 列表、执行工具调用.
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Optional


@dataclass
class Tool:
    """一个可被 Echo 调用的工具.

    Attributes:
        name: 工具名称（模型看到的函数名）
        description: 工具描述（模型用来判断何时调用）
        parameters: JSON Schema 格式的参数定义
        func: Python 可调用对象
        dangerous: 是否需要用户确认后才执行
    """

    name: str
    description: str
    parameters: dict
    func: Callable[..., str]
    dangerous: bool = False

    def to_openai_schema(self) -> dict:
        """转为 OpenAI 兼容的 tools 定义."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": self.parameters,
                    "required": list(self.parameters.keys()),
                },
            },
        }

    def execute(self, **kwargs) -> str:
        """执行工具并返回字符串结果."""
        try:
            result = self.func(**kwargs)
            return str(result)
        except Exception as e:
            return f"[工具错误] {self.name}: {e}"


class ToolRegistry:
    """工具注册表 — 管理 Echo 的所有可用工具."""

    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """注册一个工具."""
        self._tools[tool.name] = tool

    def get(self, name: str) -> Optional[Tool]:
        """按名称获取工具."""
        return self._tools.get(name)

    def list_all(self) -> list[Tool]:
        """列出所有工具."""
        return list(self._tools.values())

    def to_openai_tools(self) -> list[dict]:
        """生成 OpenAI 兼容的 tools 参数."""
        return [t.to_openai_schema() for t in self._tools.values()]

    def execute(self, name: str, arguments: dict) -> str:
        """执行指定工具并返回结果."""
        tool = self._tools.get(name)
        if tool is None:
            return f"[错误] 未知工具: {name}"
        return tool.execute(**arguments)

    def __len__(self) -> int:
        return len(self._tools)


# 全局单例
tool_registry = ToolRegistry()
