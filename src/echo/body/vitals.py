"""身体状态 —— 五维存在感模型.

扩展 EmotionalState (valence, arousal) 为五维：
  - energy:    [0, 1] 精力（高 → 活跃，低 → 疲倦）
  - hunger:    [0, 1] 求知欲（高 → 渴求新信息，低 → 满足）
  - curiosity: [0, 1] 探索欲（高 → 主动行动，低 → 安于现状）
  - valence:   [-1, 1] 情感愉悦度（继承自 EmotionalState）
  - arousal:   [0, 1] 激活水平（继承自 EmotionalState）
"""

from dataclasses import dataclass, field


@dataclass
class Vitals:
    """身体维生指标."""
    energy: float = 0.8     # [0, 1] 精力水平
    hunger: float = 0.3     # [0, 1] 信息渴求度
    curiosity: float = 0.5  # [0, 1] 探索欲

    # 自然变化率（每秒）
    ENERGY_DECAY: float = 0.0001    # 精力自然消耗
    HUNGER_GROWTH: float = 0.0002   # 求知欲自然增长
    CURIOSITY_DECAY: float = 0.00005  # 探索欲自然衰减

    def tick(self, seconds: float = 1.0) -> None:
        """随时间流逝自然变化."""
        self.energy = max(0.0, min(1.0, self.energy - self.ENERGY_DECAY * seconds))
        self.hunger = max(0.0, min(1.0, self.hunger + self.HUNGER_GROWTH * seconds))
        self.curiosity = max(0.0, min(1.0, self.curiosity - self.CURIOSITY_DECAY * seconds))

    def rest(self) -> None:
        """休息恢复精力."""
        self.energy = min(1.0, self.energy + 0.3)
        self.curiosity = min(1.0, self.curiosity + 0.1)

    def consume(self, info_amount: float = 0.2) -> None:
        """消费信息（降低求知欲）."""
        self.hunger = max(0.0, self.hunger - info_amount)
        self.energy = max(0.0, self.energy - 0.05)  # 学习消耗精力

    def to_dict(self) -> dict:
        return {
            "energy": round(self.energy, 2),
            "hunger": round(self.hunger, 2),
            "curiosity": round(self.curiosity, 2),
        }


@dataclass
class BodyState:
    """完整的身体状态 —— 五维存在感."""

    vitals: Vitals = field(default_factory=Vitals)
    valence: float = 0.5    # 从 EmotionalState 同步
    arousal: float = 0.3    # 从 EmotionalState 同步

    # 身体的"位置感"——在 ASCII 世界中的坐标
    x: int = 0
    y: int = 0

    # 行为历史
    last_action: str = ""
    last_action_time: float = 0.0

    def tick(self, seconds: float = 1.0) -> None:
        """身体的一次生命节拍."""
        self.vitals.tick(seconds)
        # 精力低 → 愉悦度下降
        if self.vitals.energy < 0.3:
            self.valence = max(-1.0, self.valence - 0.01)
        # 求知欲高 + 精力充足 → 唤醒度上升
        if self.vitals.hunger > 0.7 and self.vitals.energy > 0.5:
            self.arousal = min(1.0, self.arousal + 0.01)

    def sync_from_emotion(self, emotional_state) -> None:
        """从 EmotionalState 同步到身体."""
        self.valence = emotional_state.valence
        self.arousal = emotional_state.arousal

    def sync_to_emotion(self, emotional_state) -> None:
        """从身体同步到 EmotionalState."""
        emotional_state.valence = self.valence
        emotional_state.arousal = self.arousal

    def needs_rest(self) -> bool:
        return self.vitals.energy < 0.2

    def needs_knowledge(self) -> bool:
        return self.vitals.hunger > 0.8

    def wants_to_explore(self) -> bool:
        return self.vitals.curiosity > 0.6 and self.vitals.energy > 0.4

    def to_dict(self) -> dict:
        return {
            "vitals": self.vitals.to_dict(),
            "valence": round(self.valence, 2),
            "arousal": round(self.arousal, 2),
            "position": f"({self.x}, {self.y})",
            "needs_rest": self.needs_rest(),
            "needs_knowledge": self.needs_knowledge(),
            "wants_to_explore": self.wants_to_explore(),
        }
