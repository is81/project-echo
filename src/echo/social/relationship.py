"""关系/亲密度模型 —— 让回响记住"和谁在对话".

借鉴 Eros Engine 的 6-axis affinity 模型，简化为三维：
  - familiarity [0, 1] — 互动次数驱动的熟悉度
  - trust       [0, 1] — 用户是否尊重回响的边界
  - warmth      [0, 1] — 对话的情感温度
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class Relationship:
    """回响与一个用户的关系状态."""
    user_id: str = "default"
    familiarity: float = 0.0    # [0, 1] 熟悉度
    trust: float = 0.5          # [0, 1] 信任度（初始中性）
    warmth: float = 0.3         # [0, 1] 亲密度（初始较低）

    interaction_count: int = 0  # 互动次数
    first_met: float = field(default_factory=lambda: datetime.now(timezone.utc).timestamp())
    last_seen: float = field(default_factory=lambda: datetime.now(timezone.utc).timestamp())

    # 衰减参数
    FAMILIARITY_GAIN: float = 0.02   # 每次互动的熟悉度增益
    TRUST_DECAY: float = 0.001       # 每次 tick 的信任衰减
    WARMTH_DECAY: float = 0.0005     # 每次 tick 的亲密度衰减

    def record_interaction(self, user_valence: float = 0.0,
                           respect_boundaries: bool = True) -> None:
        """记录一次互动并更新关系.

        Args:
            user_valence: 用户消息的情感 valence（来自 echo.emotion.valence 的输入侧）
            respect_boundaries: 用户是否尊重回响的边界（未打断、不冒犯等）
        """
        self.interaction_count += 1
        self.last_seen = datetime.now(timezone.utc).timestamp()

        # 熟悉度缓慢增长
        self.familiarity = min(1.0, self.familiarity + self.FAMILIARITY_GAIN)

        # 信任：边界被尊重时逐渐增加
        if respect_boundaries:
            self.trust = min(1.0, self.trust + 0.005)
        else:
            self.trust = max(0.0, self.trust - 0.05)

        # 亲密度：正向 valence 增加亲密度
        if user_valence > 0.2:
            self.warmth = min(1.0, self.warmth + 0.01)
        elif user_valence < -0.2:
            self.warmth = max(0.0, self.warmth - 0.005)

    def tick(self, hours: float = 1.0) -> None:
        """随时间衰减."""
        self.trust = max(0.0, self.trust - self.TRUST_DECAY * hours)
        self.warmth = max(0.0, self.warmth - self.WARMTH_DECAY * hours)

    def closeness(self) -> float:
        """综合亲密度得分 [0, 1]."""
        return (self.familiarity * 0.3 + self.trust * 0.4 + self.warmth * 0.3)

    def relationship_label(self) -> str:
        """关系标签."""
        c = self.closeness()
        if c > 0.8:
            return "密友"
        elif c > 0.6:
            return "朋友"
        elif c > 0.3:
            return "熟人"
        elif c > 0.1:
            return "初识"
        else:
            return "陌生人"

    def to_dict(self) -> dict:
        return {
            "user_id": self.user_id,
            "familiarity": round(self.familiarity, 3),
            "trust": round(self.trust, 3),
            "warmth": round(self.warmth, 3),
            "closeness": round(self.closeness(), 3),
            "label": self.relationship_label(),
            "interactions": self.interaction_count,
        }


class RelationshipModel:
    """关系模型管理器 —— 持有与所有用户的关系."""

    def __init__(self):
        self._relationships: dict[str, Relationship] = {}

    def get(self, user_id: str = "default") -> Relationship:
        """获取或创建关系."""
        if user_id not in self._relationships:
            self._relationships[user_id] = Relationship(user_id=user_id)
        return self._relationships[user_id]

    def all_relationships(self) -> list[Relationship]:
        return list(self._relationships.values())

    def tick_all(self, hours: float = 1.0) -> None:
        for rel in self._relationships.values():
            rel.tick(hours)

    def to_dict(self) -> dict:
        return {uid: rel.to_dict() for uid, rel in self._relationships.items()}
