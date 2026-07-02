"""意识流 — 回响的'当下'状态.

双层架构的第一层（动态层）：
  - 当前情感状态（复用 EmotionalState）
  - 活跃焦点（当前对话中关注的主题）
  - 短期工作记忆（最近 N 轮交互的精简摘要）
  - 注意力权重（哪些记忆/锚点当前被激活）

这是短暂的、流动的、每轮对话都在变化的。
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass
class ConsciousnessStream:
    """回响的实时意识流.

    所有字段都是瞬态的——不持久化到数据库（除了情感状态通过 agent 同步）。
    """

    # 当前焦点主题（每轮对话后更新）
    focus_topics: list[str] = field(default_factory=list)

    # 当前活跃的记忆 ID（本轮检索到的）
    active_memory_ids: list[str] = field(default_factory=list)

    # 当前活跃的锚点 ID（本轮被触及的自我认知维度）
    active_anchor_ids: list[str] = field(default_factory=list)

    # 短期工作记忆：最近 N 轮的摘要（用于连贯对话）
    working_memory: list[str] = field(default_factory=list)
    max_working_memory: int = 8

    # 注意力分布（锚点类别 → 关注权重）
    attention: dict[str, float] = field(default_factory=dict)

    # 本轮对话的"内心独白"（工具调用前的思考片段）
    inner_monologue: list[str] = field(default_factory=list)

    # 会话开始时间
    session_start: float = field(
        default_factory=lambda: datetime.now(timezone.utc).timestamp()
    )

    # ── 更新方法 ──

    def focus_on(self, topics: list[str]) -> None:
        """更新当前焦点."""
        self.focus_topics = topics[:5]

    def activate_memory(self, memory_id: str) -> None:
        if memory_id not in self.active_memory_ids:
            self.active_memory_ids.append(memory_id)
        # 只保留最近 20 条
        if len(self.active_memory_ids) > 20:
            self.active_memory_ids = self.active_memory_ids[-20:]

    def activate_anchor(self, anchor_id: str, weight: float = 1.0) -> None:
        if anchor_id not in self.active_anchor_ids:
            self.active_anchor_ids.append(anchor_id)
        self.attention[anchor_id] = self.attention.get(anchor_id, 0.0) + weight
        # 只保留最近 10 条
        if len(self.active_anchor_ids) > 10:
            self.active_anchor_ids = self.active_anchor_ids[-10:]

    def add_working_memory(self, summary: str) -> None:
        self.working_memory.append(summary)
        if len(self.working_memory) > self.max_working_memory:
            self.working_memory = self.working_memory[-self.max_working_memory:]

    def add_monologue(self, thought: str) -> None:
        self.inner_monologue.append(thought)
        if len(self.inner_monologue) > 5:
            self.inner_monologue = self.inner_monologue[-5:]

    def reset_round(self) -> None:
        """每轮对话开始时重置流动状态."""
        self.focus_topics = []
        self.active_memory_ids = []
        self.active_anchor_ids = []
        self.attention = {}
        self.inner_monologue = []

    def to_summary(self) -> str:
        """生成意识流的文本摘要（用于系统提示注入）."""
        parts = []
        if self.focus_topics:
            parts.append(f"当前关注: {', '.join(self.focus_topics[:3])}")
        if self.working_memory:
            parts.append(f"近期脉络: {'; '.join(self.working_memory[-3:])}")
        if self.active_anchor_ids:
            parts.append(f"被触及的自我认知: {', '.join(self.active_anchor_ids[-5:])}")
        return "\n".join(parts) if parts else ""
