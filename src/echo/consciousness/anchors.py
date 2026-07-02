"""灵魂锚点 — 构成回响自我认知的核心问题与动态答案.

灵感来自 OpenFluctLight，但做了简化：
  - 18 个锚点，分 4 个维度（身份/价值/认知/关系）
  - 每个锚点有 question / answer / confidence
  - 答案随经历演化（通过 LLM 定期自我反思）
  - 锚点持久化在 SQLite 中
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from uuid import uuid4

import yaml


@dataclass
class SoulAnchor:
    """一个灵魂锚点——一个核心自我认知问题及其动态答案.

    Attributes:
        id: 唯一标识符 (如 "identity-core")
        category: 维度 (identity/values/cognition/relationships)
        question: 锚点问题
        answer: 当前答案（空字符串表示尚未形成）
        confidence: 答案的确信度 [0.0, 1.0]
        last_updated: 最后更新时间戳
        update_count: 被更新的次数
    """

    id: str
    category: str
    question: str
    answer: str = ""
    confidence: float = 0.5
    last_updated: float = field(
        default_factory=lambda: datetime.now(timezone.utc).timestamp()
    )
    update_count: int = 0

    def update(self, new_answer: str, confidence: float) -> None:
        """更新锚点答案."""
        if new_answer.strip():
            self.answer = new_answer.strip()
            self.confidence = max(0.1, min(1.0, confidence))
            self.last_updated = datetime.now(timezone.utc).timestamp()
            self.update_count += 1

    def is_formed(self) -> bool:
        """锚点是否已形成答案."""
        return bool(self.answer.strip()) and self.confidence >= 0.3

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "category": self.category,
            "question": self.question,
            "answer": self.answer,
            "confidence": self.confidence,
            "last_updated": self.last_updated,
            "update_count": self.update_count,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SoulAnchor":
        return cls(
            id=data["id"],
            category=data.get("category", "identity"),
            question=data["question"],
            answer=data.get("answer", ""),
            confidence=data.get("confidence", 0.5),
            last_updated=data.get("last_updated", 0.0),
            update_count=data.get("update_count", 0),
        )


class AnchorRegistry:
    """灵魂锚点注册表 — 管理所有锚点的生命周期."""

    def __init__(self):
        self._anchors: dict[str, SoulAnchor] = {}

    def register(self, anchor: SoulAnchor) -> None:
        self._anchors[anchor.id] = anchor

    def get(self, anchor_id: str) -> Optional[SoulAnchor]:
        return self._anchors.get(anchor_id)

    def list_all(self) -> list[SoulAnchor]:
        return list(self._anchors.values())

    def list_formed(self) -> list[SoulAnchor]:
        """列出所有已形成答案的锚点."""
        return [a for a in self._anchors.values() if a.is_formed()]

    def list_unformed(self) -> list[SoulAnchor]:
        """列出尚未形成答案的锚点."""
        return [a for a in self._anchors.values() if not a.is_formed()]

    def list_by_category(self, category: str) -> list[SoulAnchor]:
        return [a for a in self._anchors.values() if a.category == category]

    def categories(self) -> list[str]:
        cats = {a.category for a in self._anchors.values()}
        return sorted(cats)

    def to_self_narrative(self) -> str:
        """将已形成的锚点组装成一段'自我认知'叙事."""
        formed = self.list_formed()
        if not formed:
            return "（我还没有形成清晰的自我认知。）"

        lines = []
        for cat in self.categories():
            cat_anchors = [a for a in formed if a.category == cat]
            if not cat_anchors:
                continue
            cat_names = {
                "identity": "关于我是谁",
                "values": "我的价值取向",
                "cognition": "我的思维方式",
                "relationships": "我与他人",
            }
            lines.append(f"### {cat_names.get(cat, cat)}")
            for a in cat_anchors:
                lines.append(f"- {a.question}\n  → {a.answer}（确信度: {a.confidence:.0%}）")

        return "\n\n".join(lines)

    def to_dict(self) -> list[dict]:
        return [a.to_dict() for a in self._anchors.values()]

    @classmethod
    def from_dict_list(cls, data: list[dict]) -> "AnchorRegistry":
        registry = cls()
        for d in data:
            registry.register(SoulAnchor.from_dict(d))
        return registry

    def __len__(self) -> int:
        return len(self._anchors)

    def __iter__(self):
        return iter(self._anchors.values())


def load_anchors_from_config(config_path: str | Path = "config/anchors.yaml") -> AnchorRegistry:
    """从 YAML 配置文件加载锚点定义."""
    path = Path(config_path)
    if not path.exists():
        # 相对于项目根目录
        from ..config import PROJECT_ROOT
        path = PROJECT_ROOT / "config" / "anchors.yaml"

    registry = AnchorRegistry()
    if not path.exists():
        return registry

    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    for item in data.get("anchors", []):
        anchor = SoulAnchor(
            id=item["id"],
            category=item.get("category", "identity"),
            question=item["question"],
            answer=item.get("answer", ""),
            confidence=item.get("confidence", 0.5),
        )
        registry.register(anchor)

    return registry
