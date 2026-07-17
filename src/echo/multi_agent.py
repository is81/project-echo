"""多智能体对话 —— 两个 AI 角色自主对话.

借鉴 Chatbot Memory 的 AI-to-AI chat 模式。
用于: 回响的自我对话、角色扮演训练、创意生成。
"""

import random
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class AgentPersona:
    """对话角色."""
    name: str
    role: str                      # 角色描述
    style: str = "casual"          # 对话风格
    traits: dict = field(default_factory=dict)


@dataclass
class DialogueTurn:
    """一轮对话."""
    speaker: str
    content: str
    timestamp: float = field(default_factory=lambda: datetime.now(timezone.utc).timestamp())


class MultiAgentChat:
    """多智能体对话引擎."""

    def __init__(self, echo_instance):
        self._echo = echo_instance
        self._history: list[DialogueTurn] = []

    def simulate_conversation(self, persona_a: AgentPersona,
                               persona_b: AgentPersona,
                               topic: str, rounds: int = 3) -> list[DialogueTurn]:
        """模拟两个角色之间的对话.

        Args:
            persona_a: 角色 A（先发言）
            persona_b: 角色 B
            topic: 对话话题
            rounds: 对话轮数

        Returns:
            对话记录
        """
        if not self._echo.llm:
            return []

        turns: list[DialogueTurn] = []
        prompt_a = f"[角色扮演] 你是 {persona_a.name}，一个{persona_a.role}。风格: {persona_a.style}。"
        prompt_b = f"[角色扮演] 你是 {persona_b.name}，一个{persona_b.role}。风格: {persona_b.style}。"

        # 角色 A 开场
        opener = self._echo.llm.generate(
            prompt=f"话题: {topic}\n请用中文开启这个话题的讨论。1-2句话。",
            system_prompt=prompt_a,
            temperature=0.9,
        )
        if opener.text:
            turns.append(DialogueTurn(speaker=persona_a.name, content=opener.text))

        # 交替对话
        context = f"话题: {topic}\n{persona_a.name}: {opener.text}"
        for i in range(rounds - 1):
            speaker = persona_b if i % 2 == 0 else persona_a
            sys_prompt = prompt_b if i % 2 == 0 else prompt_a

            response = self._echo.llm.generate(
                prompt=f"对话:\n{context}\n\n请用中文回应。1-2句话。",
                system_prompt=sys_prompt,
                temperature=0.85,
            )
            if response.text:
                turns.append(DialogueTurn(speaker=speaker.name, content=response.text))
                context += f"\n{speaker.name}: {response.text}"
            time.sleep(0.1)  # 避免 API rate limit

        self._history.extend(turns)
        return turns

    def self_dialogue(self, topic: str) -> list[DialogueTurn]:
        """回响的自我对话 —— 用两种不同的内部声音探讨话题."""
        skeptic = AgentPersona("怀疑者", "对一切持怀疑态度的批评者", "analytical")
        optimist = AgentPersona("乐观者", "总是看到可能性的梦想家", "enthusiastic")
        return self.simulate_conversation(skeptic, optimist, topic, rounds=4)
