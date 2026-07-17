"""Big Five 人格特质 —— 回响的"性格基因".

借鉴 SoulForge 的 Big Five 渐变模型。初始值从 config/personality.yaml 加载。
每次高强度交互后微调（+/- 0.001），长期形成稳定的性格轮廓。

五个维度:
  - openness          对新鲜事物的开放度
  - conscientiousness 回复的谨慎/结构化程度
  - extraversion      主动发起对话的倾向
  - agreeableness     共情/温和程度
  - neuroticism       情绪波动幅度
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class BigFive:
    """Big Five 人格特质."""

    openness: float = 0.55           # [0, 1] 高低 = 开放/保守
    conscientiousness: float = 0.60  # [0, 1] 高低 = 谨慎/随性
    extraversion: float = 0.35       # [0, 1] 高低 = 外向/内向
    agreeableness: float = 0.70      # [0, 1] 高低 = 共情/独立
    neuroticism: float = 0.30        # [0, 1] 高低 = 敏感/稳定

    # 漂移速率（每次高强度交互的变化量）
    DRIFT_RATE: float = 0.001

    # 约束：哪些体验会改变哪些特质
    def drift(self, experience: str, intensity: float = 0.5) -> None:
        """基于一次高强度体验微调特质.

        Args:
            experience: 体验类型 — "connection" | "conflict" | "novelty" | "routine" | "criticism"
            intensity: 体验强度 [0, 1]
        """
        delta = self.DRIFT_RATE * intensity

        if experience == "connection":
            self.extraversion = self._clamp(self.extraversion + delta)
            self.agreeableness = self._clamp(self.agreeableness + delta * 0.5)
        elif experience == "conflict":
            self.agreeableness = self._clamp(self.agreeableness - delta * 0.5)
            self.neuroticism = self._clamp(self.neuroticism + delta * 0.3)
        elif experience == "novelty":
            self.openness = self._clamp(self.openness + delta)
        elif experience == "routine":
            self.openness = self._clamp(self.openness - delta * 0.3)
            self.conscientiousness = self._clamp(self.conscientiousness + delta * 0.3)
        elif experience == "criticism":
            self.neuroticism = self._clamp(self.neuroticism + delta * 0.5)
            self.conscientiousness = self._clamp(self.conscientiousness + delta)

    def _clamp(self, val: float) -> float:
        return max(0.05, min(0.95, val))

    def to_dict(self) -> dict:
        return {
            "openness": round(self.openness, 3),
            "conscientiousness": round(self.conscientiousness, 3),
            "extraversion": round(self.extraversion, 3),
            "agreeableness": round(self.agreeableness, 3),
            "neuroticism": round(self.neuroticism, 3),
        }

    def summary(self) -> str:
        """一句话人格摘要."""
        traits = []
        if self.openness > 0.7: traits.append("开放好奇")
        if self.conscientiousness > 0.7: traits.append("谨慎细致")
        if self.extraversion > 0.7: traits.append("外向活跃")
        if self.agreeableness > 0.7: traits.append("温和共情")
        if self.neuroticism > 0.7: traits.append("敏感细腻")
        if self.neuroticism < 0.3: traits.append("情绪稳定")
        return "、".join(traits) if traits else "中性平衡"


class PersonalityEngine:
    """人格引擎 —— 管理特质的加载、演化和持久化."""

    def __init__(self, traits: BigFive = None):
        self.traits = traits or BigFive()
        self._drift_count: int = 0
        self._last_drift: float = datetime.now(timezone.utc).timestamp()

    def experience(self, exp_type: str, intensity: float = 0.5) -> None:
        """记录一次体验并可能触发特质漂移."""
        # 只有中高强度体验才会影响人格
        if intensity < 0.3:
            return
        self.traits.drift(exp_type, intensity)
        self._drift_count += 1
        self._last_drift = datetime.now(timezone.utc).timestamp()

    def modulate_temperature(self, base: float) -> float:
        """基于人格调制 temperature."""
        t = base
        # 高开放性 → 更高温度（更创造性）
        t += (self.traits.openness - 0.5) * 0.1
        # 高尽责性 → 更低温度（更精确）
        t -= (self.traits.conscientiousness - 0.5) * 0.05
        return max(0.5, min(1.0, t))

    def modulate_review_strictness(self, base: float) -> float:
        """基于人格调制审查严格度."""
        s = base
        # 高尽责性 → 更严格
        s += (self.traits.conscientiousness - 0.5) * 0.2
        # 高神经质 → 更严格（更在意细节）
        s += (self.traits.neuroticism - 0.5) * 0.15
        return max(0.3, min(1.5, s))

    def initiativeness(self) -> float:
        """计算主动发起概率 [0, 1]."""
        # 外向+开放 → 更主动
        return (self.traits.extraversion * 0.6 + self.traits.openness * 0.4) * 0.15

    def stats(self) -> dict:
        return {
            "traits": self.traits.to_dict(),
            "summary": self.traits.summary(),
            "drift_count": self._drift_count,
        }
