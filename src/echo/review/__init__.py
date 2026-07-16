"""审查模块 (Orbitofrontal Cortex) —— 输出前的自我审查回路.

在 LLM 生成草稿后、输出到用户前，对回复进行多维度审查：
- 原则对齐度（是否违反基因原则）
- 情绪一致性（是否与当前 mood 匹配）
- 诚实度（是否在假装知道）
- 简洁度（是否过度啰嗦）
- 空洞度（是否在说正确的废话）
"""

from .critique import CritiqueEngine, CritiqueResult

__all__ = ["CritiqueEngine", "CritiqueResult"]
