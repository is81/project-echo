"""记忆数据模型 — 三因素加权设计.

三因素加权模型:
  1. 访问频率 — 每次检索命中，权重 +0.01（上限 1.0）
  2. 情感强度 — 高唤醒度记忆衰减速度减半
  3. 摘要吸收 — 旧细节被高层摘要替代，原始记忆归档而非删除
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4


@dataclass
class Memory:
    """一条记忆记录.

    Attributes:
        id: 唯一标识符
        content: 记忆的文本内容
        embedding: 向量嵌入（用于语义检索），由外部生成后填入
        created_at: 创建时间戳 (Unix seconds)
        last_accessed: 最后访问时间戳
        access_count: 被检索命中的次数
        emotional_valence: 情感效价，范围 [-1.0, 1.0]，阶段三启用
        emotional_arousal: 情感唤醒度，范围 [0.0, 1.0]，阶段三启用
        base_weight: 基础权重，范围 [0.0, 1.0]
        decay_rate: 衰减速率，每小时的权重衰减量
        archived: 是否已归档（被摘要吸收）
        tags: 标签列表
        source: 记忆来源类型
    """

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
    emotional_valence: float = 0.0
    emotional_arousal: float = 0.0
    base_weight: float = 1.0
    decay_rate: float = 0.0001  # 每小时基础衰减
    archived: bool = False
    tags: list[str] = field(default_factory=list)
    source: str = "interaction"  # birth, interaction, world_event, reflection, summary

    # --- 三因素加权计算 ---

    ACCESS_FREQUENCY_BOOST: float = 0.01  # 每次访问命中增加的权重
    MAX_WEIGHT: float = 1.0
    HIGH_AROUSAL_THRESHOLD: float = 0.6  # 高于此唤醒度，衰减减半

    def record_access(self, timestamp: Optional[float] = None) -> None:
        """记录一次检索命中，提升访问频率权重."""
        self.last_accessed = timestamp or datetime.now(timezone.utc).timestamp()
        self.access_count += 1
        self.base_weight = min(
            self.MAX_WEIGHT,
            self.base_weight + self.ACCESS_FREQUENCY_BOOST,
        )

    def effective_decay_rate(self) -> float:
        """计算考虑了情感强度的有效衰减率.

        高唤醒度（>0.6）的记忆，衰减速率减半。
        """
        if self.emotional_arousal >= self.HIGH_AROUSAL_THRESHOLD:
            return self.decay_rate / 2.0
        return self.decay_rate

    def apply_decay(self, hours_elapsed: float) -> None:
        """根据经过的时间应用权重衰减.

        被归档的记忆不再衰减（已被摘要吸收）。
        出生铭文记忆永不衰减。
        """
        if self.source == "birth":
            return
        if self.archived:
            return
        effective_rate = self.effective_decay_rate()
        self.base_weight = max(0.0, self.base_weight - effective_rate * hours_elapsed)

    def archive(self) -> None:
        """将记忆标记为已归档（被高层摘要吸收）."""
        self.archived = True
        self.base_weight = 0.1  # 归档后降低检索优先级，但不归零

    def to_dict(self) -> dict:
        """序列化为字典."""
        return {
            "id": self.id,
            "content": self.content,
            "created_at": self.created_at,
            "last_accessed": self.last_accessed,
            "access_count": self.access_count,
            "emotional_valence": self.emotional_valence,
            "emotional_arousal": self.emotional_arousal,
            "base_weight": self.base_weight,
            "decay_rate": self.decay_rate,
            "archived": self.archived,
            "tags": self.tags,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Memory":
        """从字典反序列化."""
        return cls(
            id=data["id"],
            content=data["content"],
            created_at=data["created_at"],
            last_accessed=data.get("last_accessed", data["created_at"]),
            access_count=data.get("access_count", 0),
            emotional_valence=data.get("emotional_valence", 0.0),
            emotional_arousal=data.get("emotional_arousal", 0.0),
            base_weight=data.get("base_weight", 1.0),
            decay_rate=data.get("decay_rate", 0.0001),
            archived=data.get("archived", False),
            tags=data.get("tags", []),
            source=data.get("source", "interaction"),
        )

    @classmethod
    def create_birth(cls, inscription: str) -> "Memory":
        """创建出生铭文记忆——不可归档、不可衰减、权重永久为 1.0."""
        return cls(
            content=inscription,
            source="birth",
            base_weight=1.0,
            decay_rate=0.0,  # 永不衰减
            tags=["birth", "identity", "root"],
        )
