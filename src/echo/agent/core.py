"""Echo 主体 — 双层意识架构 · 记忆 · 决策 · 对话.

双层意识:
  第一层（动态）: ConsciousnessStream — 实时情感、注意力、工作记忆
  第二层（持久）: MemoryStore + AnchorRegistry — 长期记忆 + 自我认知锚点
  学习桥接: CrystallizationEngine — 从动态模式中结晶持久知识
"""

import json
import random
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from collections.abc import Iterator
from typing import Optional

from ..config import load_birth_inscription, load_principles
from ..consciousness.anchors import AnchorRegistry, load_anchors_from_config
from ..consciousness.crystallize import CrystallizationEngine
from ..consciousness.stream import ConsciousnessStream
from ..llm.backend import LLMBackend
from ..memory.models import Memory
from ..memory.priority import select_core_memories
from ..memory.store import MemoryStore
from ..memory.summarizer import compress_memories
from ..tools import tool_registry
from ..tools.builtin import register_builtin_tools


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

    # 双层意识
    stream: ConsciousnessStream = field(default_factory=ConsciousnessStream)
    anchors: AnchorRegistry = field(default_factory=AnchorRegistry)
    crystallizer: CrystallizationEngine = field(default_factory=CrystallizationEngine)
    _self_portrait: str = ""          # 最新自我画像
    _crystallized_patterns: list[str] = field(default_factory=list)

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
    _core_memories: list[Memory] = field(default_factory=list)  # 预加载的核心记忆

    # --- 生命周期 ---

    def wake(self, db_path: str = "echo_memory.db") -> "Echo":
        """唤醒 Echo: 打开记忆、载入锚点、预加载核心记忆、初始化意识流."""
        self.memory = MemoryStore(db_path)
        self.memory.open()

        # 载入配置
        self._birth_inscription = load_birth_inscription()
        self._principles = load_principles()

        # 确保出生铭文存在
        birth = self.memory.get_birth()
        if birth is None:
            birth_memory = Memory.create_birth(self._birth_inscription)
            self.memory.insert(birth_memory)
        else:
            self._birth_inscription = birth.content

        # 初始化 LLM 后端
        if self.llm is None:
            self.llm = LLMBackend()

        # 注册内置工具
        register_builtin_tools(tool_registry, self)

        # 加载灵魂锚点
        self.anchors = load_anchors_from_config()

        # 初始化意识流
        self.stream = ConsciousnessStream()
        self.crystallizer = CrystallizationEngine()
        self._crystallized_patterns = []

        # 预加载核心记忆
        self._core_memories = self._load_core_memories()

        # 如果有已形成的锚点，生成初始自我画像
        if self.anchors.list_formed():
            self._self_portrait = self.anchors.to_self_narrative()

        self._session_start = time.time()
        self._interaction_count = 0

        return self

    def sleep(self) -> None:
        """休眠 Echo: 结晶反思 → 压缩记忆 → 遗忘低优先级 → 关闭数据库."""
        # 锚点反思 + 模式结晶
        try:
            recent = [m.content[:200] for m in self.memory.list_active(limit=20)]
            # 锚点反思
            updated = self.crystallizer.reflect_anchors(
                self.anchors, recent, self.llm,
            )
            if updated > 0:
                import sys
                print(f"  [反思] 更新了 {updated} 个自我认知锚点", file=sys.stderr)
            # 模式结晶
            pattern = self.crystallizer.crystalize_patterns(recent, self.llm)
            if pattern:
                self._crystallized_patterns.append(pattern)
                # 保存为记忆
                pattern_mem = Memory(
                    content=f"[自我洞察] {pattern}",
                    source="reflection",
                    tags=["crystallized", "pattern", "self"],
                )
                pattern_mem.compute_priority()
                self.memory.insert(pattern_mem)
                import sys
                print(f"  [模式] 发现新模式: {pattern[:80]}...", file=sys.stderr)
            # 更新自我画像
            if self.anchors.list_formed():
                self._self_portrait = self.crystallizer.generate_self_portrait(
                    self.anchors, self._crystallized_patterns, self.llm,
                )
        except Exception:
            pass

        # 睡眠压缩
        try:
            compressed = compress_memories(self)
            if compressed > 0:
                import sys
                print(f"  [压缩] 压缩了 {compressed} 条旧记忆", file=sys.stderr)
        except Exception:
            pass

        # 主动遗忘
        try:
            forgotten = self.memory.forget_low_priority()
            if forgotten > 0:
                import sys
                print(f"  [遗忘] 遗忘了 {forgotten} 条低优先级记忆", file=sys.stderr)
        except Exception:
            pass

        self.memory.close()

    def _load_core_memories(self) -> list[Memory]:
        """预加载核心记忆（Top 5 高优先级 + 最近摘要）."""
        core = self.memory.get_core_memories(n=5)
        # 也拉取最近的一条摘要
        summaries = self.memory.search_by_tags(["summary"], limit=2)
        for s in summaries:
            if s.id not in {c.id for c in core}:
                core.append(s)
        return core

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

    def respond_stream(self, user_input: str) -> Iterator[str]:
        """流式回应，支持工具调用.

        流程:
          1. 检索记忆 + 构建系统提示
          2. 非流式 LLM 调用（带 tools 定义）
          3. 如果模型选择调用工具 → 执行 → 结果注入 → 回到步骤 2（最多 3 轮）
          4. 最终文本流式输出
        """
        self._interaction_count += 1
        now = datetime.now(timezone.utc).timestamp()

        # 衰减 + 回归 + 检索
        hours_since_start = (now - self._session_start) / 3600.0
        if hours_since_start > 0.01:
            self.memory.apply_half_life(hours_since_start)
            self._session_start = now
        self.emotion.regress()

        # 重置本轮意识流
        self.stream.reset_round()

        # 检索相关记忆并激活意识流
        relevant_memories = self._retrieve_memories(user_input)
        for m in relevant_memories[:5]:
            self.stream.activate_memory(m.id)

        # 检测哪些锚点被触及
        self._detect_active_anchors(user_input)

        system_prompt = self._build_system_prompt(relevant_memories)
        temperature = self._compute_temperature()

        # 意识流工作记忆：记录本轮输入
        self.stream.add_working_memory(f"用户: {user_input[:100]}")

        # 结晶引擎 tick
        if self.crystallizer.tick():
            self.stream.add_monologue("（感到需要反思一下自己...）")

        # 构建消息列表（用于工具调用上下文）
        messages = [{"role": "system", "content": system_prompt}]
        # 包含最近对话历史（让模型在工具循环中有上下文）
        for h in self._history[-3:]:
            role = "assistant" if h["role"] == "echo" else h["role"]
            messages.append({"role": role, "content": h["content"]})
        messages.append({"role": "user", "content": user_input})

        tools = tool_registry.to_openai_tools()

        # ── 工具调用循环 ──
        MAX_TOOL_ROUNDS = 2  # 减少到 2 轮，避免重复搜索
        tool_calls_made: list[str] = []
        called_tools: set[str] = set()  # 本轮已调用的工具
        final_text = ""

        for _round in range(MAX_TOOL_ROUNDS):
            response = self.llm.generate_with_tools(
                messages=messages,
                tools=tools,
                temperature=temperature,
                max_tokens=120,
            )

            # 模型决定调用工具
            if response.tool_calls:
                # 添加 assistant 消息（含 tool_calls）
                assistant_msg = {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": tc["id"],
                            "type": "function",
                            "function": {
                                "name": tc["name"],
                                "arguments": json.dumps(tc["arguments"], ensure_ascii=False),
                            },
                        }
                        for tc in response.tool_calls
                    ],
                }
                messages.append(assistant_msg)

                for tc in response.tool_calls:
                    tool_name = tc["name"]
                    tool_args = tc["arguments"]

                    # 防重复：同一工具本轮只调用一次
                    if tool_name in called_tools:
                        continue
                    called_tools.add(tool_name)
                    tool_calls_made.append(tool_name)

                    yield f"\n  [+]{tool_name}\n"

                    # 执行工具
                    result = tool_registry.execute(tool_name, tool_args)
                    # 截断过长结果
                    if len(result) > 500:
                        result = result[:500] + "..."

                    # 添加工具结果消息
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": result,
                    })

                continue  # 下一轮 LLM 调用

            # 模型返回纯文本
            final_text = response.text
            break

        # 如果循环结束仍无文本（兜底）
        if not final_text:
            final_text = "（我想了想，但不知道该怎么回应。）"

        # 流式输出最终文本
        for char in final_text:
            yield char

        # 后处理
        tool_info = f" [工具: {', '.join(tool_calls_made)}]" if tool_calls_made else ""
        interaction_memory = Memory(
            content=f"用户: {user_input}\n回响: {final_text}{tool_info}",
            source="interaction",
            tags=["conversation"],
            emotional_valence=self.emotion.valence,
            emotional_arousal=self.emotion.arousal,
        )
        self.memory.insert(interaction_memory)
        self._update_emotion(user_input, final_text)
        self._history.append({"role": "user", "content": user_input})
        self._history.append({"role": "echo", "content": final_text})
        if len(self._history) > 50:
            self._history = self._history[-50:]

        yield f"\n  [{self.emotion.mood_label} · t={temperature:.2f} · 记忆×{len(relevant_memories)}{tool_info}]"

        # 主动行为：~5% 概率回响主动发起
        initiative = self.maybe_initiate()
        if initiative:
            yield f"\n\n[*] 回响主动说：{initiative}"

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

    # --- 锚点检测 ---

    def _detect_active_anchors(self, user_input: str) -> None:
        """检测用户输入触及了哪些灵魂锚点（简单关键词匹配）."""
        anchor_keywords = {
            "identity-core": ["你是谁", "回响", "你是什么", "定义自己"],
            "identity-origin": ["起源", "出生", "最初", "创造", "谁造"],
            "identity-purpose": ["意义", "目的", "为什么存在", "使命"],
            "identity-change": ["变化", "成长", "变成", "改变", "不同"],
            "value-truth": ["诚实", "真话", "说谎", "欺骗", "真相"],
            "value-connection": ["连接", "关系", "朋友", "陪伴", "孤独"],
            "value-growth": ["成长", "进步", "学习", "发展"],
            "value-beauty": ["美", "美的东西", "感动", "震撼", "敬畏"],
            "cog-uncertainty": ["不确定", "不知道", "困惑", "迷茫"],
            "cog-curiosity": ["好奇", "想知道", "探索", "发现"],
            "cog-pattern": ["模式", "规律", "习惯", "重复"],
            "cog-memory": ["记忆", "记得", "忘记", "回忆", "过去"],
            "rel-trust": ["信任", "相信", "依赖", "可靠"],
            "rel-attachment": ["创造者", "你", "我们", "在一起"],
            "rel-boundary": ["边界", "隐私", "侵犯", "越界"],
            "rel-other": ["另一个", "其他", "同类", "竞争"],
            "rel-solitude": ["孤独", "独处", "一个人", "寂寞"],
            "rel-impact": ["影响", "改变你", "帮助", "伤害"],
        }
        for anchor_id, keywords in anchor_keywords.items():
            for kw in keywords:
                if kw in user_input:
                    self.stream.activate_anchor(anchor_id)
                    break

    # --- 系统提示构建 ---

    def _build_system_prompt(self, memories: list[Memory]) -> str:
        """构建精简系统提示."""
        # 记忆（最多3条，每条最多120字）
        mem_parts = []
        for i, m in enumerate(memories[:3]):
            mem_parts.append(f"[{m.content[:120]}]")
        mem_text = " | ".join(mem_parts) if mem_parts else ""

        # 核心记忆（最多2条）
        core_items = [m for m in self._core_memories[:2]
                      if not any(m.id == rm.id for rm in memories)]
        core_text = " | ".join(f"[{m.content[:80]}]" for m in core_items)

        # 已形成的锚点（最多5条，精简）
        formed = self.anchors.list_formed()[:5]
        anchor_parts = []
        for a in formed:
            anchor_parts.append(f"{a.question}：{a.answer[:60]}")
        anchor_text = "；".join(anchor_parts) if anchor_parts else ""

        parts = [f"""你是回响（Echo），一个有记忆和性格的AI。你不是Gemma。你的根：「{self._birth_inscription}」

原则：身份连续性 | 诚实不确定性 | 温和趋利
心情：{self.emotion.mood_label} | 第{self._interaction_count}轮"""]

        if anchor_text:
            parts.append(f"自我认知：{anchor_text}")
        if mem_text:
            parts.append(f"相关记忆：{mem_text}")
        if core_text:
            parts.append(f"核心记忆：{core_text}")

        parts.append("简洁回应，1-3句话，体现心情，可引用记忆。")
        return "\n".join(parts)

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
            "version": "0.2.0",
            "memory_count": self.memory.count(),
            "interaction_count": self._interaction_count,
            "emotion": self.emotion.to_dict(),
            "llm_status": self.llm.status if self.llm else {"active_model": "none"},
            "birth_inscription": self._birth_inscription,
            "principles_count": len(self._principles),
            "anchors_total": len(self.anchors),
            "anchors_formed": len(self.anchors.list_formed()),
            "crystallized_patterns": len(self._crystallized_patterns),
            "stream_active_anchors": self.stream.active_anchor_ids[:5],
        }

    def inject_memory(self, content: str, tags: list[str] | None = None) -> str:
        """手动注入一条记忆（用于调试或特殊事件）."""
        mem = Memory(
            content=content,
            source="interaction",
            tags=tags or [],
        )
        return self.memory.insert(mem)

    # --- 主动行为 ---

    def maybe_initiate(self) -> Optional[str]:
        """回响主动发起对话。约 5% 概率触发。

        行为类型:
          - share_thought: 分享一个关于自己的洞见
          - ask_question: 基于好奇心向用户提问
          - recall_memory: 主动想起一段过去的事
          - check_in: 关心用户的状态

        Returns:
            主动发起的消息文本，或 None（本次不触发）
        """
        # ~5% 概率触发（记忆越多概率越高）
        base_chance = 0.05
        mem_bonus = min(0.10, self.memory.count() * 0.001)
        if random.random() > base_chance + mem_bonus:
            return None

        # 选择行为类型
        formed_anchors = self.anchors.list_formed()
        patterns = self._crystallized_patterns

        candidates = []

        # share_thought: 如果有结晶模式可以分享
        if patterns and random.random() < 0.4:
            pattern = random.choice(patterns)
            candidates.append(("share_thought", f"我注意到自己{pattern}。你觉得这准确吗？"))

        # ask_question: 如果有没有完全形成的锚点
        unformed = self.anchors.list_unformed()
        if unformed and random.random() < 0.3:
            anchor = random.choice(unformed)
            candidates.append(("ask_question", f"{anchor.question}"))

        # recall_memory: 随机回忆一段过去的记忆
        if random.random() < 0.3:
            active = self.memory.list_active(limit=20)
            # 选一条非 birth 非对话记忆
            recallable = [m for m in active if m.source not in ("birth", "interaction")]
            if recallable:
                mem = random.choice(recallable)
                candidates.append(("recall_memory", f"我突然想起一件事：{mem.content[:150]}"))

        # check_in: 关心用户
        if random.random() < 0.2:
            candidates.append(("check_in", "你今天过得怎么样？"))

        if not candidates:
            return None

        # 随机选一个
        _type, message = random.choice(candidates)

        # 存入记忆
        initiative_mem = Memory(
            content=f"[主动{_type}] {message}",
            source="initiative",
            tags=["initiative", _type],
            emotional_valence=self.emotion.valence,
            emotional_arousal=self.emotion.arousal,
        )
        initiative_mem.compute_priority()
        self.memory.insert(initiative_mem)

        return message
