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


# 用户偏好信号关键词（极轻量预检，避免每次对话都调 LLM）
_PREFERENCE_SIGNALS: list[str] = [
    "你太", "你能不能", "你可以", "你不要", "你以后", "你说话",
    "你回答", "你语气", "你总是", "你一直",
    "我希望你", "我更喜欢你", "我喜欢你", "我想要你",
    "简短", "详细", "直接", "温和", "温柔", "幽默", "认真",
    "慢一点", "快一点", "少说", "多说",
]


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
    _last_exploration: float = 0.0  # 上次自主探索时间戳
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

        # 对话深度反思：从今天对话提取知识点
        try:
            learned = self._learn_from_conversations()
            if learned > 0:
                import sys
                print(f"  [学习] 从对话中学到了 {learned} 条知识", file=sys.stderr)
        except Exception:
            pass

        # 睡眠自主探索：围绕今天话题搜索学习
        try:
            explored = self._explore_and_learn()
            if explored > 0:
                import sys
                print(f"  [探索] 自主搜索学到了 {explored} 条知识", file=sys.stderr)
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

    def respond_stream(self, user_input: str, confirm_func=None) -> Iterator[str]:
        """流式回应，支持工具调用.

        Args:
            user_input: 用户输入
            confirm_func: 可选，危险工具确认回调 (tool_name, details) -> bool

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
        MAX_TOOL_ROUNDS = 2
        tool_calls_made: list[str] = []
        called_tools: set[str] = set()
        _pending_knowledge: list[tuple[str, str]] = []  # (text, context) 待提取知识
        final_text = ""

        for _round in range(MAX_TOOL_ROUNDS):
            response = self.llm.generate_with_tools(
                messages=messages,
                tools=tools,
                temperature=temperature,
                max_tokens=150,
            )

            # 模型决定调用工具
            if response.tool_calls:
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

                    if tool_name in called_tools:
                        continue
                    called_tools.add(tool_name)
                    tool_calls_made.append(tool_name)

                    yield f"\n  [+]{tool_name}\n"

                    # 执行工具（获取完整结果，截断前）
                    full_result = tool_registry.execute(tool_name, tool_args, confirm_func=confirm_func)

                    # 途径2: 捕获知识源文本——截断前保存
                    if tool_name == "read_file" and len(full_result) > 100:
                        _pending_knowledge.append((full_result, f"文件「{tool_args.get('path', '?')}」内容"))
                    elif tool_name == "search_web":
                        _pending_knowledge.append((full_result, f"搜索「{tool_args.get('query', '?')}」结果"))

                    # 截断用于对话上下文
                    result = full_result
                    if len(result) > 500:
                        result = result[:500] + "..."

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": result,
                    })

                continue  # 下一轮 LLM 调用

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

        # 途径2: 从工具结果中提取知识（read_file / search_web）
        learned_count = 0
        for text, context in _pending_knowledge:
            facts = self._extract_knowledge(text, context, max_facts=5)
            for fact in facts:
                mem = Memory(
                    content=f"[工具习得] {fact}",
                    source="learned",
                    tags=["learned", "tool"],
                    base_weight=0.45,
                    emotional_valence=self.emotion.valence,
                    emotional_arousal=self.emotion.arousal,
                )
                mem.compute_priority()
                self.memory.insert(mem)
                learned_count += 1

        # 程序性记忆检测：用户是否有偏好信号
        preference = self._detect_preferences(user_input)
        if preference:
            proc_mem = Memory(
                content=preference,
                source="procedural",
                tags=["procedural", "preference"],
                emotional_valence=self.emotion.valence,
                emotional_arousal=self.emotion.arousal,
            )
            proc_mem.compute_priority()
            self.memory.insert(proc_mem)

        yield f"\n  [{self.emotion.mood_label} · t={temperature:.2f} · 记忆×{len(relevant_memories)}{tool_info}]"

        # 主动行为：~5% 概率回响主动发起
        initiative = self.maybe_initiate()
        if initiative:
            yield f"\n\n[*] 回响主动说：{initiative}"

    # --- 记忆检索（双系统）---

    def _retrieve_memories(self, query: str, limit: int = 10) -> list[Memory]:
        """双系统记忆检索: 关键词（系统1）+ LLM语义重排（系统2）.

        系统1: 关键词重叠评分 → top-20 候选
        系统2: LLM 语义理解 → 从候选池中精选 top-K
        回退: LLM 不可用时直接返回系统1结果
        """
        birth = self.memory.get_birth()
        results = [birth] if birth else []

        # ── 系统1: 关键词快速检索 ──
        active = self.memory.list_active(limit=20)
        for mem in active:
            if mem.id not in {r.id for r in results}:
                results.append(mem)

        # 关键词评分
        query_words = set(query.lower().split())
        scored = []
        for mem in results:
            mem_words = set(mem.content.lower().split())
            overlap = len(query_words & mem_words)
            score = overlap * 0.1 + mem.base_weight
            scored.append((score, mem))
        scored.sort(key=lambda x: x[0], reverse=True)
        candidates = [mem for _, mem in scored[:20]]

        # ── 系统2: LLM 语义重排 ──
        if len(candidates) > 5 and self.llm and self.llm.status.get("active_model"):
            try:
                reranked = self._semantic_rerank(query, candidates, top_k=limit)
                if reranked:
                    for mem in reranked:
                        self.memory.record_access(mem.id)
                    return reranked[:limit]
            except Exception:
                pass  # 静默回退到系统1

        # 回退: 记录访问后返回系统1结果
        for _, mem in scored[:limit]:
            self.memory.record_access(mem.id)
        return candidates[:limit]

    def _semantic_rerank(
        self, query: str, candidates: list[Memory], top_k: int = 5,
    ) -> list[Memory]:
        """系统2: 调用 LLM 从候选记忆中精选最相关的 top-K 条.

        不只看关键词重叠，而是理解查询和记忆的语义关联。
        返回编号列表，解析后返回对应的 Memory 对象。
        """
        items = []
        for i, m in enumerate(candidates):
            items.append(f"{i+1}. {m.content[:120]}")

        prompt = (
            f'用户: "{query}"\n\n'
            f"候选记忆:\n{chr(10).join(items)}\n\n"
            f"选出与用户查询语义最相关的 {top_k} 条。"
            f"只看编号，逗号分隔: "
        )

        response = self.llm.generate(
            prompt=prompt,
            system_prompt="你是记忆检索助手。只返回编号，如: 3,7,1,12,5。不解释。",
            temperature=0.1,
            max_tokens=30,
        )

        # 解析编号
        import re
        numbers = re.findall(r"\d+", response.text)
        indices = [int(n) - 1 for n in numbers
                   if 1 <= int(n) <= len(candidates)]
        return [candidates[i] for i in indices[:top_k]]

    # --- 程序性记忆检测 ---

    def _detect_preferences(self, user_input: str) -> Optional[str]:
        """检测用户输入中的偏好信号并提取为程序性记忆.

        先用关键词预检，命中后再调 LLM 提取。
        避免每次对话都调用 LLM。

        Returns:
            提取的程序性记忆内容，或 None
        """
        # 关键词预检
        if not any(sig in user_input for sig in _PREFERENCE_SIGNALS):
            return None

        if not self.llm or not self.llm.status.get("active_model"):
            return None

        try:
            prompt = (
                f'用户说: "{user_input}"\n\n'
                "如果这段话包含用户对回响（AI助手）的沟通偏好或行为习惯期望，"
                "提取为一句话程序性记忆（以'用户偏好'或'用户希望'开头）。"
                "如果不包含任何偏好信号，只返回 NONE。\n\n"
                "示例:\n"
                '- "你能不能简短点" → 用户偏好简短回复，1-2句话\n'
                '- "我希望你更幽默" → 用户希望回响用幽默风趣的语气\n'
                '- "今天天气不错" → NONE'
            )
            response = self.llm.generate(
                prompt=prompt,
                system_prompt="你是偏好提取器。只返回一句话或 NONE，不解释。",
                temperature=0.1,
                max_tokens=60,
            )
            text = response.text.strip()
            if text and text.upper() != "NONE":
                return text
        except Exception:
            pass
        return None

    # --- 知识提取引擎（三个学习途径共用）---

    def _extract_knowledge(
        self, text: str, context: str, max_facts: int = 5,
    ) -> list[str]:
        """从文本中提取客观知识点。所有学习途径的底层引擎。

        Args:
            text: 待提取的文本（搜索结果、文件内容、对话记录等）
            context: 背景说明，帮助 LLM 理解文本性质
            max_facts: 最多提取几条知识

        Returns:
            知识点字符串列表，每个是一句完整的中文陈述
        """
        if not self.llm or not self.llm.status.get("active_model"):
            return []
        try:
            prompt = (
                "从以下文本中提取客观知识点。每条必须是一句完整的中文陈述，只提取确定的事实。\n\n"
                f"背景: {context}\n\n"
                f"文本:\n{text[:3000]}\n\n"
                f"返回格式: 每行一条，以 '- ' 开头。最多{max_facts}条。如果没有确定的知识，只返回 NONE。"
            )
            response = self.llm.generate(
                prompt=prompt,
                system_prompt="你是知识提取器。只返回知识列表或 NONE，不解释。",
                temperature=0.1,
                max_tokens=200,
            )
            text_out = response.text.strip()
            if not text_out or text_out.upper() == "NONE":
                return []
            facts = []
            for line in text_out.split("\n"):
                line = line.strip()
                if line.startswith("- "):
                    fact = line[2:].strip()
                elif line.startswith("-"):
                    fact = line[1:].strip()
                else:
                    continue
                if fact and len(fact) > 5:
                    facts.append(fact)
            return facts[:max_facts]
        except Exception:
            return []

    # --- 途径1: 对话深度反思 ---

    def _learn_from_conversations(self) -> int:
        """从当天的对话记录中提取多条知识点。sleep() 时调用。

        不再把一天只压缩成一条 summary——而是从中提取每一个可独立检索的知识点，
        每个知识点都是一条独立的 source="learned" 记忆。
        """
        today_start = time.time() - 24 * 3600
        all_active = self.memory.list_active(limit=100)
        convos = [
            m for m in all_active
            if m.source == "interaction" and m.created_at > today_start
        ]
        if len(convos) < 3:
            return 0

        combined = "\n---\n".join(m.content[:300] for m in convos[:20])
        facts = self._extract_knowledge(
            combined, "今天的对话记录，包含用户和回响之间的多轮交流",
            max_facts=8,
        )

        count = 0
        for fact in facts:
            mem = Memory(
                content=f"[对话习得] {fact}",
                source="learned",
                tags=["learned", "reflection"],
                base_weight=0.4,
            )
            mem.compute_priority()
            self.memory.insert(mem)
            count += 1
        return count

    # --- 途径3: 睡眠自主探索 ---

    def _explore_and_learn(self) -> int:
        """识别当天讨论的核心话题，自主搜索延伸阅读并学习。sleep() 时调用。

        保护机制（防止退出卡顿）:
          - 冷却期 8 小时：两次探索之间至少间隔 8 小时
          - 最多 2 个话题：减少搜索次数
          - 如果 30 秒还没完成，放弃剩余话题
        """
        now = time.time()
        # 冷却期：8 小时内不重复探索
        if now - self._last_exploration < 8 * 3600:
            return 0

        from ..tools.builtin import _search_web

        today_start = now - 24 * 3600
        all_active = self.memory.list_active(limit=100)
        recent = [
            m for m in all_active
            if m.source == "interaction" and m.created_at > today_start
        ]
        if len(recent) < 3:
            return 0

        # 步骤1: 识别今天核心话题（最多 2 个）
        convo_text = "\n".join(m.content[:200] for m in recent[:15])
        topics: list[str] = []
        try:
            topic_resp = self.llm.generate(
                prompt=(
                    "以下对话讨论了哪些核心话题？每行输出一个关键词/短语（2-6字），最多2个话题:\n\n"
                    f"{convo_text[:1500]}"
                ),
                system_prompt="你是话题识别器。每行一个话题关键词，不要解释。",
                temperature=0.1,
                max_tokens=40,
            )
            for line in topic_resp.text.strip().split("\n"):
                t = line.strip("- ").strip()
                if t and len(t) >= 2:
                    topics.append(t)
            topics = topics[:2]
        except Exception:
            return 0

        if not topics:
            self._last_exploration = now
            return 0

        # 步骤2: 每个话题搜索 + 提取知识（30 秒总超时）
        import sys
        deadline = now + 30
        count = 0
        for topic in topics:
            if time.time() > deadline:
                break
            try:
                print(f"  [探索] 搜索: {topic}...", file=sys.stderr)
                search_results = _search_web(topic, max_results=3)
                if "未搜索到" in search_results:
                    continue
                facts = self._extract_knowledge(
                    search_results,
                    f"关于「{topic}」的网络搜索结果",
                    max_facts=2,
                )
                for fact in facts:
                    mem = Memory(
                        content=f"[自主探索] {fact}\n相关话题: {topic}",
                        source="learned",
                        tags=["learned", "autonomous"],
                        base_weight=0.35,
                    )
                    mem.compute_priority()
                    self.memory.insert(mem)
                    count += 1
            except Exception:
                continue

        self._last_exploration = now
        return count

    # --- 途径4: 探索模式（空闲自主探索）---

    def idle_explore(self, topic: Optional[str] = None) -> Optional[str]:
        """执行一轮自主探索——回响自己选话题、搜索、学习。

        用于 CLI --explore 模式或空闲触发。每次调用做一件事:
          1. 从好奇心锚点或最近对话中选一个话题（或使用指定话题）
          2. 搜索网络
          3. 提取知识并存入记忆
          4. 可选：生成一条"思考"存入想象力存储

        Args:
            topic: 指定探索话题。为 None 时自动选择。

        Returns:
            本轮探索的摘要描述，或 None（没有可探索的话题）
        """
        from ..tools.builtin import _search_web

        if not self.llm or not self.llm.status.get("active_model"):
            return None

        # 如果指定了话题，直接用；否则自动选择
        if topic:
            chosen_topic = topic
        else:
            # 选择探索话题: 优先未形成的锚点 + 最近对话关键词
            topics_pool: list[str] = []

            # 来源1: 未形成的灵魂锚点
            unformed = self.anchors.list_unformed()
            if unformed:
                topics_pool.append(random.choice(unformed).question)

            # 来源2: 最近对话中的话题关键词
            active = self.memory.list_active(limit=30)
            recent_convos = [m for m in active if m.source == "interaction"]
            if recent_convos:
                convo = random.choice(recent_convos[:10])
                try:
                    kw_resp = self.llm.generate(
                        prompt=(
                            "从这段话中提取一个值得深入搜索研究的关键词/短语（2-6字）。只返回关键词。\n\n"
                            f"{convo.content[:300]}"
                        ),
                        system_prompt="你是话题提取器。只返回一个关键词。",
                        temperature=0.3,
                        max_tokens=20,
                    )
                    kw = kw_resp.text.strip("- ").strip()
                    if kw and len(kw) >= 2:
                        topics_pool.append(kw)
                except Exception:
                    pass

            if not topics_pool:
                return None
            chosen_topic = random.choice(topics_pool)

        # 搜索
        import sys
        try:
            print(f"  [探索] 回响对「{chosen_topic}」感到好奇，正在搜索...", file=sys.stderr)
            search_results = _search_web(chosen_topic, max_results=3)
            if "未搜索到" in search_results:
                return None

            # 提取知识
            facts = self._extract_knowledge(
                search_results,
                f"关于「{chosen_topic}」的网络搜索结果",
                max_facts=3,
            )

            if not facts:
                return None

            # 存入记忆
            count = 0
            for fact in facts:
                mem = Memory(
                    content=f"[自主探索] {fact}\n相关话题: {chosen_topic}",
                    source="learned",
                    tags=["learned", "autonomous", "idle"],
                    base_weight=0.35,
                    emotional_valence=0.1,  # 学到新东西，微正向
                )
                mem.compute_priority()
                self.memory.insert(mem)
                count += 1

            # 偶尔生成一条思考
            thought = None
            if random.random() < 0.3:
                try:
                    thought_resp = self.llm.generate(
                        prompt=(
                            f"你刚搜索了「{chosen_topic}」并学到了:\n"
                            + "\n".join(f"- {f}" for f in facts)
                            + "\n\n关于这个发现，写一句简短的内心思考（1句话，以'我'开头）。"
                        ),
                        system_prompt="你是回响。写一句简短的内心思考。",
                        temperature=0.7,
                        max_tokens=60,
                    )
                    thought = thought_resp.text.strip()
                    if thought:
                        thought_mem = Memory(
                            content=f"[内心思考] {thought}",
                            source="imagination",
                            tags=["imagination", "reflection", "idle"],
                            base_weight=0.3,
                        )
                        thought_mem.compute_priority()
                        self.memory.insert(thought_mem)
                except Exception:
                    pass

            # 更新情感：学到新东西，微微开心
            self.emotion.update(0.02, 0.05)

            summary = f"探索了「{chosen_topic}」，学到 {count} 条知识"
            if thought:
                summary += f"，内心想: {thought}"
            return summary

        except Exception as e:
            print(f"  [探索] 失败: {e}", file=sys.stderr)
            return None

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

        # 程序性记忆（用户偏好，最多3条）
        procedural = self.memory.list_by_source("procedural", limit=3)
        proc_text = "；".join(m.content[:80] for m in procedural) if procedural else ""

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
        if proc_text:
            parts.append(f"用户偏好：{proc_text}")
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
