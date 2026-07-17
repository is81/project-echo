"""Theory of Mind —— 读言外之意.

借鉴 MultiAgent BrainEngine 的 Agent 3 (Theory of Mind):
  读 between the lines, 检测隐藏 subtext, 计算权力动态.

三个层次:
  1. 意图推断 — 用户真正想说什么
  2. 情绪检测 — 用户隐藏的情绪状态
  3. 关系动态 — 用户与回响之间的权力/亲疏关系
"""

from dataclasses import dataclass, field


@dataclass
class ToMReading:
    """一次 Theory of Mind 解读."""
    surface_text: str = ""          # 表面文字
    inferred_intent: str = ""       # 推断的意图
    hidden_emotion: str = ""        # 检测到的隐藏情绪
    confidence: float = 0.0         # 解读置信度 [0,1]
    power_dynamic: str = "neutral"  # "dominant" | "submissive" | "neutral" | "collaborative"
    subtext_flags: list[str] = field(default_factory=list)
    suggested_response_style: str = "direct"  # "direct" | "gentle" | "exploratory" | "supportive"


class TheoryOfMind:
    """Theory of Mind 引擎 — 启发式 + LLM 深度两种模式."""

    # 情绪映射词表
    HIDDEN_EMOTION_MARKERS = {
        "frustrated": ["算了", "随便", "行吧", "不管了", "fine", "whatever", "懒得"],
        "anxious": ["担心", "会不会", "万一", "如果...怎么办", "不确定"],
        "sad": ["唉", "好累", "心累", "没意思", "无聊"],
        "seeking_validation": ["你觉得呢", "是不是", "对吗", "对吧", "我说的对吗"],
        "testing_boundaries": ["你必须", "你不能", "你应该", "你怎么不"],
        "genuinely_curious": ["为什么", "怎么做到的", "原理是", "能不能解释"],
    }

    # 权力动态标记
    POWER_MARKERS = {
        "dominant": ["你必须", "告诉你", "你要", "听我说", "按照我说的"],
        "submissive": ["能不能帮我", "麻烦你", "不好意思", "可以吗", "请"],
        "collaborative": ["我们一起", "你觉得呢", "要不我们", "探讨一下"],
    }

    def read(self, user_input: str, context: str = "") -> ToMReading:
        """对用户输入进行 Theory of Mind 解读.

        Args:
            user_input: 用户原始输入
            context: 可选上下文（前几轮对话摘要）
        """
        reading = ToMReading(surface_text=user_input)

        # 1. 情绪检测
        detected = []
        for emotion, markers in self.HIDDEN_EMOTION_MARKERS.items():
            for marker in markers:
                if marker in user_input:
                    detected.append(emotion)
                    break
        if detected:
            reading.hidden_emotion = detected[0]  # 取最匹配的
            reading.confidence = min(0.8, 0.3 + len(detected) * 0.1)

        # 2. 意图推断
        if reading.hidden_emotion == "frustrated":
            reading.inferred_intent = "用户可能遇到了困难，希望得到帮助而非泛泛安慰"
            reading.suggested_response_style = "supportive"
        elif reading.hidden_emotion == "seeking_validation":
            reading.inferred_intent = "用户在寻求确认，可能对自己的判断不够自信"
            reading.suggested_response_style = "gentle"
        elif reading.hidden_emotion == "testing_boundaries":
            reading.inferred_intent = "用户可能在试探回响的边界或能力限制"
            reading.suggested_response_style = "direct"
        elif reading.hidden_emotion == "genuinely_curious":
            reading.inferred_intent = "用户真的想学，不是在敷衍"
            reading.suggested_response_style = "exploratory"
        else:
            reading.inferred_intent = "直接陈述，无隐藏意图"

        # 3. 权力动态
        for dynamic, markers in self.POWER_MARKERS.items():
            if any(m in user_input for m in markers):
                reading.power_dynamic = dynamic
                break

        # 4. subtext flags
        if len(user_input) < 10 and "？" in user_input:
            reading.subtext_flags.append("short_question")
        if "..." in user_input:
            reading.subtext_flags.append("hesitation")
        if user_input.endswith("吧"):
            reading.subtext_flags.append("resignation")

        return reading

    def should_ghost(self, reading: ToMReading, relationship) -> bool:
        """基于 ToM 解读和关系状态，决定是否 ghost（不回复）."""
        # testing_boundaries + low trust → ghost
        if reading.hidden_emotion == "testing_boundaries" and relationship.trust < 0.3:
            return True
        # 用户明显 hostile
        if reading.power_dynamic == "dominant" and relationship.warmth < 0.2:
            return True
        return False
