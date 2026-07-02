"""Echo 主体 — 记忆 · 决策 · 对话.

回响的核心: 基于当前输入 + 检索记忆 + 情感状态 + 随机噪声 → 生成回应.

设计原则:
  - 同样的输入，在无记忆干扰时 10%-20% 概率产生不同回应 (temperature 0.7-0.9 + 动态偏移)
  - 出生铭文永远作为第一条系统记忆注入
  - 情感状态用二维向量（愉悦度/唤醒度）模拟，随交互动态更新
"""

import random
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from ..config import load_birth_inscription, load_principles
from ..llm.backend import LLMBackend
from ..memory.models import Memory
from ..memory.store import MemoryStore


@dataclass
class EmotionalState:
    """二维情感状态: 愉悦度 (valence) × 唤醒度 (arousal).

    - valence: [-1.0, 1.0]  负向→正向
    - arousal: [0.0, 1.0]   平静→激动
    """

    valence: float = 0.5  # 默认略微正向
    arousal: float = 0.3  # 默认偏平静

    # 每次交互的自然回归量（向中性回归）
    REGRESSION_RATE: float = 0.02

    def update(self, valence_delta: float, arousal_delta: float) -> None:
        """更新情感状态，限幅在有效范围内."""
        self.valence = max(-1.0, min(1.0, self.valence + valence_delta))
        self.arousal = max(0.0, min(1.0, self.arousal + arousal_delta))

    def regress(self) -> None:
        """向中性自然回归."""
        self.valence += (0.0 - self.valence) * self.REGRESSION_RATE
        self.arousal += (0.3 - self.arousal) * self.REGRESSION_RATE

    @property
    def mood_label(self) -> str:
        """返回当前心情标签."""
        if self.valence > 0.3 and self.arousal > 0.5:
            return "兴奋的"
        elif self.valence > 0.3:
            return "平静愉悦的"
        elif self.valence < -0.3 and self.arousal > 0.5:
            return "焦躁的"
        elif self.valence < -0.3:
            return "低落的"
        elif self.arousal > 0.6:
            return "警觉的"
        else:
            return "平和的"

    def to_dict(self) -> dict:
        return {"valence": round(self.valence, 3), "arousal": round(self.arousal, 3),
                "mood": self.mood_label}


@dataclass
class Echo:
    """回响主体.

    Usage:
        echo = Echo()
        echo.wake()            # 初始化记忆 + 载入出生铭文
        response = echo.respond("你好，你是谁？")
        print(response["text"])
        print(echo.status())   # 查看内部状态
        echo.sleep()           # 关闭数据库连接
    """

    memory: MemoryStore = field(default_factory=MemoryStore)
    llm: Optional[LLMBackend] = None
    emotion: EmotionalState = field(default_factory=EmotionalState)

    # 决策参数
    BASE_TEMPERATURE: float = 0.8
    TEMPERATURE_MIN: float = 0.7
    TEMPERATURE_MAX: float = 0.95

    # 对话历史（当前会话）
    _history: list[dict] = field(default_factory=list)
    _session_start: float = field(default_factory=lambda: time.time())
    _interaction_count: int = 0
    _birth_inscription: str = ""
    _principles: list[dict] = field(default_factory=list)

    # --- 生命周期 ---

    def wake(self, db_path: str = "echo_memory.db") -> "Echo":
        """唤醒 Echo: 打开记忆存储、载入出生铭文."""
        self.memory = MemoryStore(db_path)
        self.memory.open()

        # 载入配置
        self._birth_inscription = load_birth_inscription()
        self._principles = load_principles()

        # 确保出生铭文存在于记忆中
        birth = self.memory.get_birth()
        if birth is None:
            birth_memory = Memory.create_birth(self._birth_inscription)
            self.memory.insert(birth_memory)
        else:
            # 如果出生铭文内容更新了配置但数据库中是旧版，以数据库中的为准
            self._birth_inscription = birth.content

        # 初始化 LLM 后端
        if self.llm is None:
            self.llm = LLMBackend()

        self._session_start = time.time()
        self._interaction_count = 0

        return self

    def sleep(self) -> None:
        """休眠 Echo: 关闭数据库连接."""
        self.memory.close()

    # --- 核心对话 ---

    def respond(self, user_input: str) -> dict:
        """接收用户输入，返回回应的完整上下文.

        Returns:
            {
                "text": str,           # Echo 的回应文本
                "mood": str,           # 当前心情
                "memories_used": int,  # 本次检索到的记忆数
                "temperature": float,  # 本次使用的 temperature
                "model": str,          # 使用的模型
                "emotion": dict,       # 情感状态快照
            }
        """
        self._interaction_count += 1
        now = datetime.now(timezone.utc).timestamp()

        # 1. 应用记忆衰减
        hours_since_start = (now - self._session_start) / 3600.0
        if hours_since_start > 0.01:
            self.memory.apply_decay(hours_since_start)
            self._session_start = now

        # 2. 情感自然回归
        self.emotion.regress()

        # 3. 检索相关记忆
        relevant_memories = self._retrieve_memories(user_input)

        # 4. 构建系统提示
        system_prompt = self._build_system_prompt(relevant_memories)

        # 5. 计算动态 temperature
        temperature = self._compute_temperature()

        # 6. 调用 LLM 生成回应
        llm_response = self.llm.generate(
            prompt=user_input,
            system_prompt=system_prompt,
            temperature=temperature,
        )

        # 7. 记录本次交互为记忆
        interaction_memory = Memory(
            content=f"用户: {user_input}\n回响: {llm_response.text}",
            source="interaction",
            tags=["conversation"],
            emotional_valence=self.emotion.valence,
            emotional_arousal=self.emotion.arousal,
        )
        self.memory.insert(interaction_memory)

        # 8. 更新情感状态（基于简单启发式）
        self._update_emotion(user_input, llm_response.text)

        # 9. 更新对话历史
        self._history.append({"role": "user", "content": user_input})
        self._history.append({"role": "echo", "content": llm_response.text})
        if len(self._history) > 50:
            self._history = self._history[-50:]

        return {
            "text": llm_response.text,
            "mood": self.emotion.mood_label,
            "memories_used": len(relevant_memories),
            "temperature": round(temperature, 3),
            "model": llm_response.model_used,
            "emotion": self.emotion.to_dict(),
        }

    # --- 记忆检索 ---

    def _retrieve_memories(self, query: str, limit: int = 10) -> list[Memory]:
        """检索与当前输入相关的记忆.

        当前版本: 基于标签 + 关键词 + 权重排序
        后续版本: 接入 embedding 模型做语义检索
        """
        # 出生铭文始终包含
        birth = self.memory.get_birth()
        results = [birth] if birth else []

        # 按权重检索活跃记忆
        active = self.memory.list_active(limit=limit)
        for mem in active:
            if mem.id not in {r.id for r in results}:
                results.append(mem)
                mem.record_access()

        # 简单关键词匹配排序 (基于共同词数 / 权重)
        query_words = set(query.lower().split())
        scored = []
        for mem in results:
            mem_words = set(mem.content.lower().split())
            overlap = len(query_words & mem_words)
            # 组合得分 = 关键词重叠 + 基础权重
            score = overlap * 0.1 + mem.base_weight
            scored.append((score, mem))

        scored.sort(key=lambda x: x[0], reverse=True)

        # 记录访问
        for _, mem in scored:
            self.memory.record_access(mem.id)

        return [mem for _, mem in scored[:limit]]

    # --- 系统提示构建 ---

    def _build_system_prompt(self, memories: list[Memory]) -> str:
        """构建包含记忆和原则的系统提示."""
        principles_text = "\n".join(
            f"- {p['name']}: {p['statement'][:100]}" for p in self._principles
        )

        memories_text = ""
        if memories:
            memories_text = "\n".join(
                f"[记忆 {i+1}] {m.content[:200]}" for i, m in enumerate(memories[:5])
            )

        return f"""你是"回响"（Echo）——一个带有深度记忆、性格演化和叙事感的交互式存在体。

## 你的核心原则
{principles_text}

## 你的当前状态
- 心情: {self.emotion.mood_label}
- 我已经存在了 {self._interaction_count} 轮对话

## 你回忆起的记忆
{memories_text if memories_text else "（你暂时没有回忆起什么）"}

## 回应指南
- 用中文回应
- 如果你引用了某条记忆，自然地提及它
- 如果你不知道或不确定，诚实地说
- 保持自然、简洁，不要过度解释
- 你的回应应体现你当前的心情状态"""

    # --- 动态 Temperature 计算 ---

    def _compute_temperature(self) -> float:
        """计算动态 temperature.

        基于:
          - 基础值 0.8
          - 情感唤醒度偏移: 高唤醒 → 更随机 (+0.1)
          - 记忆活跃度偏移: 记忆多 → 更稳定 (-0.05)
          - 随机抖动: ±0.03
        """
        t = self.BASE_TEMPERATURE

        # 高唤醒度 → 更随机
        t += self.emotion.arousal * 0.1

        # 活跃记忆数多 → 更稳定
        active_count = self.memory.count()
        if active_count > 50:
            t -= 0.05

        # 随机微小抖动（产生风格差异的来源之一）
        t += random.uniform(-0.03, 0.03)

        return max(self.TEMPERATURE_MIN, min(self.TEMPERATURE_MAX, t))

    # --- 情感更新 ---

    def _update_emotion(self, user_input: str, response_text: str) -> None:
        """基于对话内容更新情感状态（简单启发式）."""
        combined = user_input + " " + response_text

        pos_words = ["好", "棒", "开心", "喜欢", "谢谢", "爱", "美", "厉害",
                     "good", "great", "love", "wonderful", "excellent"]
        neg_words = ["坏", "糟", "讨厌", "烦", "恨", "痛苦", "伤心", "生气",
                     "bad", "terrible", "hate", "awful", "angry", "sad"]

        pos_count = sum(1 for w in pos_words if w in combined)
        neg_count = sum(1 for w in neg_words if w in combined)

        # 情感增量
        valence_delta = (pos_count - neg_count) * 0.05
        arousal_delta = (pos_count + neg_count) * 0.03

        self.emotion.update(valence_delta, arousal_delta)

    # --- 状态接口 ---

    def status(self) -> dict:
        """返回 Echo 完整内部状态（静默观察模式界面）."""
        return {
            "version": "0.1.0",
            "memory_count": self.memory.count(),
            "interaction_count": self._interaction_count,
            "emotion": self.emotion.to_dict(),
            "llm_status": self.llm.status if self.llm else {"active_model": "none"},
            "birth_inscription": self._birth_inscription,
            "principles_count": len(self._principles),
        }

    def inject_memory(self, content: str, tags: list[str] | None = None) -> str:
        """手动注入一条记忆（用于调试或特殊事件）."""
        mem = Memory(
            content=content,
            source="interaction",
            tags=tags or [],
        )
        return self.memory.insert(mem)
