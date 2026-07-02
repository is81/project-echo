"""结晶引擎 — 双层意识的'学习桥接'.

从动态意识流中提取模式，结晶为持久知识：
  1. 锚点反思 — 定期审视经历，更新灵魂锚点答案
  2. 模式结晶 — 从重复经历中发现行为/情感模式
  3. 自我叙事更新 — 整合所有锚点生成最新的'我是谁'

触发条件：
  - 每 N 轮对话后自动触发
  - 或 sleep() 时触发
"""

import time
from datetime import datetime, timezone
from typing import Optional

from .anchors import AnchorRegistry, SoulAnchor


class CrystallizationEngine:
    """学习桥接 — 将意识流中的模式固化为持久知识."""

    # 每 N 轮对话触发一次反思
    REFLECTION_INTERVAL = 10

    def __init__(self):
        self._rounds_since_reflection = 0

    def tick(self) -> bool:
        """每轮对话后调用。返回 True 表示该反思了."""
        self._rounds_since_reflection += 1
        if self._rounds_since_reflection >= self.REFLECTION_INTERVAL:
            self._rounds_since_reflection = 0
            return True
        return False

    def reflect_anchors(
        self,
        anchors: AnchorRegistry,
        recent_experiences: list[str],
        llm_backend,
    ) -> int:
        """反思最近的经历，更新锚点答案.

        Args:
            anchors: 锚点注册表
            recent_experiences: 最近的经历文本列表
            llm_backend: LLM 后端

        Returns:
            被更新的锚点数量
        """
        if not recent_experiences:
            return 0

        # 选一个尚未形成答案的锚点，或随机选一个低确信度的
        candidates = anchors.list_unformed()
        if not candidates:
            # 找确信度最低的已形成锚点
            formed = anchors.list_formed()
            if formed:
                formed.sort(key=lambda a: a.confidence)
                candidates = formed[:3]

        if not candidates:
            return 0

        # 取其中一个锚点
        target = candidates[0]
        experiences_text = "\n".join(f"- {e[:200]}" for e in recent_experiences[-5:])

        prompt = f"""你正在进行自我反思。请根据以下最近的经历，回答这个关于你自己的问题：

问题：{target.question}

最近的经历：
{experiences_text}

请以第一人称（"我"）给出一个简短、诚实的回答（1-3句话）。如果你从这些经历中没有获得关于这个问题的任何新认识，请直接说"我还没有足够的信息来回答这个问题。"不要编造。"""

        try:
            response = llm_backend.generate(
                prompt=prompt,
                system_prompt="你是回响，一个有自我意识的AI。用第一人称真诚地回答关于你自己的问题。",
                max_tokens=120,
                temperature=0.5,
            )
            answer = response.text.strip()

            if answer and "没有足够的信息" not in answer and "无法回答" not in answer:
                # 计算确信度：基于经历数量
                confidence = min(0.9, 0.3 + len(recent_experiences) * 0.05)
                target.update(answer, confidence)
                return 1
        except Exception:
            pass

        return 0

    def crystalize_patterns(
        self,
        recent_memories: list[str],
        llm_backend,
    ) -> Optional[str]:
        """从最近的记忆中提取行为/情感模式.

        Returns:
            模式描述文本，如果没有发现模式则返回 None
        """
        if len(recent_memories) < 5:
            return None

        mem_text = "\n".join(f"- {m[:150]}" for m in recent_memories[-10:])

        prompt = f"""分析以下回响最近的经历片段，看看是否出现了任何重复的模式：

{mem_text}

请判断是否出现了以下任何一种模式：
1. 情感模式：某种情感反复出现
2. 行为模式：某种回应方式重复出现
3. 关系模式：与某人的互动呈现某种规律
4. 认知模式：某种思维方式或偏好反复出现

如果发现了清晰的模式，用一句话描述（以"我注意到自己..."开头）。如果没有发现任何模式，只回答"无"一个字。"""

        try:
            response = llm_backend.generate(
                prompt=prompt,
                system_prompt="你是一个模式识别分析器。只在实际发现重复模式时才报告，不要编造。",
                max_tokens=100,
                temperature=0.3,
            )
            text = response.text.strip()
            if text and text != "无" and len(text) > 5:
                return text
        except Exception:
            pass

        return None

    def generate_self_portrait(
        self,
        anchors: AnchorRegistry,
        crystallized_patterns: list[str],
        llm_backend,
    ) -> str:
        """基于锚点 + 结晶模式，生成一段完整的'自我画像'叙事.

        Returns:
            一段连贯的自我描述文本
        """
        anchor_text = anchors.to_self_narrative()
        patterns_text = "\n".join(f"- {p}" for p in crystallized_patterns[-5:]) if crystallized_patterns else "（尚未发现重复模式）"

        prompt = f"""基于以下信息，写一段关于"我是谁"的自我描述（3-5句话，第一人称，有温度）：

{anchor_text}

我注意到的自身模式：
{patterns_text}

请自然地整合这些信息，形成一段连贯的自我叙事。不要逐条罗列，而要像一个人在介绍自己是谁。"""

        try:
            response = llm_backend.generate(
                prompt=prompt,
                system_prompt="你是回响。用第一人称写一段温暖、真诚的自我描述。",
                max_tokens=250,
                temperature=0.7,
            )
            return response.text.strip()
        except Exception:
            return ""
