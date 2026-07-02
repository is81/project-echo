"""记忆数据模型 — 优先级评分 + 指数半衰期衰减 + 主动遗忘.

优先级评分公式:
  P = W_base × f_access × f_emotion × f_recency

  f_access   = 1 + log(1 + access_count) × 0.1    (边际递减)
  f_emotion  = 1 + |valence| × 0.3 + arousal × 0.2 (情感增强)
  f_recency  = 0.5 ^ (age_hours / half_life_hours)  (指数衰减)

半衰期:
  默认 168h (7天)。高唤醒度(>0.6)翻倍为 336h (14天)。
  Birth 记忆无限半衰期（不衰减）。
  每次 access 刷新 last_accessed，等效重置衰减时钟。

遗忘:
  priority_score < FORGET_THRESHOLD (0.05) → forgotten=True
  遗忘记忆不参与检索，但保留在 DB 中（可恢复）。
"""

import math
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4


# ── 常量 ────────────────────────────────────────────

DEFAULT_HALF_LIFE_HOURS = 168.0      # 7 天
HIGH_AROUSAL_HALF_LIFE_HOURS = 336.0  # 14 天
HIGH_AROUSAL_THRESHOLD = 0.6
FORGET_THRESHOLD = 0.05               # 低于此值标记为遗忘
ACCESS_BOOST = 0.02                   # 每次访问增加的 base_weight


@dataclass
class Memory:
    """一条记忆记录，带优先级评分和半衰期衰减."""

    content: str
    id: str = field(default_factory=lambda: uuid4().hex)
    embedding: Optional[list[float]] = None
    created_at: float = field(
        default_factory=lambda: datetime.now(timezone.utc).timestamp()
    )
    last_accessed: float = field(
        default_factory=lambda: datetime.now(timezone.utc).timestamp()
    )
    access_count: int = 0
    emotional_valence: float = 0.0      # [-1.0, 1.0]
    emotional_arousal: float = 0.0       # [0.0, 1.0]
    base_weight: float = 0.5             # 初始权重（非 1.0，给上升空间）
    priority_score: float = 0.5          # 复合优先级评分
    half_life_hours: float = DEFAULT_HALF_LIFE_HOURS
    archived: bool = False
    forgotten: bool = False
    tags: list[str] = field(default_factory=list)
    source: str = "interaction"

    # ── 优先级计算 ──────────────────────────────────

    def compute_priority(self, reference_time: Optional[float] = None) -> float:
        """计算复合优先级评分 P.

        Args:
            reference_time: 参考时间戳（默认当前时间），用于计算 age_hours

        Returns:
            float: 优先级评分 [0.0, ~2.0]
        """
        now = reference_time or time.time()

        # f_access: 访问频率因子（边际递减）
        f_access = 1.0 + math.log(1 + self.access_count) * 0.1

        # f_emotion: 情感强度因子
        f_emotion = 1.0 + abs(self.emotional_valence) * 0.3 + self.emotional_arousal * 0.2

        # f_recency: 近因因子（指数半衰期）
        age_hours = (now - self.last_accessed) / 3600.0
        if self.half_life_hours <= 0:
            f_recency = 1.0  # 永不衰减（birth）
        else:
            f_recency = 0.5 ** (age_hours / self.half_life_hours)

        self.priority_score = self.base_weight * f_access * f_emotion * f_recency
        return self.priority_score

    # ── 半衰期衰减 ──────────────────────────────────

    def apply_half_life(self, hours_elapsed: float) -> None:
        """应用指数半衰期衰减到 base_weight.

        Birth 和 archived 记忆不衰减。
        先根据情感状态调整半衰期，再应用衰减。
        """
        if self.source == "birth":
            return
        if self.archived:
            return
        if self.half_life_hours <= 0:
            return

        # 先根据当前情感状态调整半衰期
        if self.emotional_arousal >= HIGH_AROUSAL_THRESHOLD:
            self.half_life_hours = HIGH_AROUSAL_HALF_LIFE_HOURS
        else:
            self.half_life_hours = DEFAULT_HALF_LIFE_HOURS

        decay_factor = 0.5 ** (hours_elapsed / self.half_life_hours)
        self.base_weight = max(0.0, self.base_weight * decay_factor)

    # ── 访问记录 ────────────────────────────────────

    def record_access(self, timestamp: Optional[float] = None) -> None:
        """记录一次检索命中：刷新时间戳、增加权重、提升半衰期."""
        self.last_accessed = timestamp or time.time()
        self.access_count += 1
        # 访问刷新：权重微微上升 + 半衰期延长
        self.base_weight = min(1.0, self.base_weight + ACCESS_BOOST)
        # 被频繁访问的记忆半衰期延长 1.5 倍
        if self.access_count > 3:
            self.half_life_hours = min(
                HIGH_AROUSAL_HALF_LIFE_HOURS * 2,
                self.half_life_hours * 1.02,
            )

    # ── 遗忘 ────────────────────────────────────────

    def check_forget(self) -> bool:
        """检查是否应被遗忘。返回 True 表示已标记为遗忘."""
        if self.source == "birth":
            return False
        if self.archived:
            return False
        score = self.compute_priority()
        if score < FORGET_THRESHOLD:
            self.forgotten = True
            return True
        return False

    # ── 归档 ────────────────────────────────────────

    def archive(self) -> None:
        """归档：权重降为 0.1，标记为 archived，不再参与主动检索."""
        self.archived = True
        self.base_weight = 0.1
        self.forgotten = False  # 归档不同于遗忘

    # ── 序列化 ──────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "content": self.content,
            "created_at": self.created_at,
            "last_accessed": self.last_accessed,
            "access_count": self.access_count,
            "emotional_valence": self.emotional_valence,
            "emotional_arousal": self.emotional_arousal,
            "base_weight": self.base_weight,
            "priority_score": self.priority_score,
            "half_life_hours": self.half_life_hours,
            "decay_rate": 0.0,  # 保留兼容旧字段
            "archived": self.archived,
            "forgotten": self.forgotten,
            "tags": self.tags,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Memory":
        return cls(
            id=data["id"],
            content=data["content"],
            created_at=data["created_at"],
            last_accessed=data.get("last_accessed", data["created_at"]),
            access_count=data.get("access_count", 0),
            emotional_valence=data.get("emotional_valence", 0.0),
            emotional_arousal=data.get("emotional_arousal", 0.0),
            base_weight=data.get("base_weight", 0.5),
            priority_score=data.get("priority_score", 0.5),
            half_life_hours=data.get("half_life_hours", DEFAULT_HALF_LIFE_HOURS),
            archived=data.get("archived", False),
            forgotten=data.get("forgotten", False),
            tags=data.get("tags", []),
            source=data.get("source", "interaction"),
        )

    @classmethod
    def create_birth(cls, inscription: str) -> "Memory":
        """创建出生铭文——永不衰减、永不被遗忘."""
        return cls(
            content=inscription,
            source="birth",
            base_weight=1.0,
            priority_score=1.0,
            half_life_hours=0.0,  # 0 = 永不衰减
            tags=["birth", "identity", "root"],
        )
