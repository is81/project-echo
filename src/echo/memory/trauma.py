"""创伤印记 —— 当威胁超过韧性阈值时形成长期情绪偏置.

借鉴 Anthropomorphic Agent Engine 的 trauma imprinting:
  - trauma node 在 threat > resilience 时形成
  - 长期偏置 emotional state
  - 相似场景触发时重新激活
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class TraumaNode:
    """一个创伤印记."""
    id: str
    trigger_keywords: list[str]      # 触发关键词
    emotional_shift: tuple[float, float]  # (valence_delta, arousal_delta) 触发时的情绪偏移
    formed_at: float = field(default_factory=lambda: datetime.now(timezone.utc).timestamp())
    intensity: float = 0.5           # [0, 1] 创伤强度
    reactivation_count: int = 0      # 被重新激活的次数
    safety_learned: bool = False     # 是否通过安全经验学习到该创伤已不再危险

    def reactivate(self) -> tuple[float, float]:
        """重新激活——返回情绪偏移."""
        if self.safety_learned:
            return (0.0, 0.0)
        self.reactivation_count += 1
        # 每次重新激活，强度略微衰减
        decay = 0.95 ** self.reactivation_count
        return (
            self.emotional_shift[0] * self.intensity * decay,
            self.emotional_shift[1] * self.intensity * decay,
        )


class TraumaRegistry:
    """创伤印记注册表."""

    def __init__(self, resilience_threshold: float = 0.7):
        self._traumas: list[TraumaNode] = []
        self._resilience_threshold = resilience_threshold
        # 韧性: 高 → 不容易形成创伤

    def evaluate(self, threat_level: float, keywords: list[str],
                 emotional_impact: tuple[float, float]) -> bool:
        """评估一个事件是否形成创伤印记.

        Args:
            threat_level: 威胁强度 [0, 1]
            keywords: 事件关键词
            emotional_impact: (valence_delta, arousal_delta) 当前情绪变化

        Returns:
            True 如果形成了新创伤
        """
        if threat_level > self._resilience_threshold:
            node = TraumaNode(
                id=f"trauma-{len(self._traumas)}",
                trigger_keywords=keywords,
                emotional_shift=emotional_impact,
                intensity=threat_level,
            )
            self._traumas.append(node)
            return True
        return False

    def scan_triggers(self, text: str) -> list[TraumaNode]:
        """扫描文本，返回被触发的创伤印记."""
        triggered = []
        for t in self._traumas:
            if any(kw in text for kw in t.trigger_keywords):
                triggered.append(t)
        return triggered

    def learn_safety(self, trauma_id: str) -> None:
        """通过安全经验学习——标记创伤已不再危险."""
        for t in self._traumas:
            if t.id == trauma_id:
                t.safety_learned = True
                break

    def active_count(self) -> int:
        return sum(1 for t in self._traumas if not t.safety_learned)

    def to_dict(self) -> dict:
        return {
            "total": len(self._traumas),
            "active": self.active_count(),
            "resilience": self._resilience_threshold,
        }
