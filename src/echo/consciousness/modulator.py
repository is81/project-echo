"""情绪调制器 —— Limbic System 硬化.

将二维情感状态（valence × arousal）转化为各模块的运行时参数偏移。
这是情绪模块从"只是一个标签"进化为"真正的跨模块权重偏移器"的关键一步。

每个模块读取自己关心的参数，在运行时根据参数调整行为。
"""

from dataclasses import dataclass, field


@dataclass
class ModuleParams:
    """各模块的运行时调制参数.

    由 EmotionalState 每轮计算一次，注入各模块。
    所有参数都是乘数或偏移量，1.0 = 无调制。
    """

    # ── 审查模块调制 ──
    review_strictness: float = 1.0    # > 1.0 = 更严格（pass 阈值更低）
    review_confidence_bias: float = 0.0  # 额外偏移

    # ── 记忆模块调制 ──
    memory_emotional_boost: float = 1.0  # 情感记忆权重乘数
    memory_recall_depth: int = 20        # 检索记忆数量

    # ── 规划模块调制 ──
    planning_aggressiveness: float = 1.0  # > 1.0 = 更多步骤、更大胆
    planning_max_steps: int = 5          # 计划最大步骤数

    # ── 工具模块调制 ──
    tool_risk_tolerance: float = 1.0     # < 1.0 = 减少危险工具使用
    tool_curiosity: float = 1.0          # > 1.0 = 更频繁主动探索

    # ── 语言模块调制 ──
    language_temperature_bias: float = 0.0   # 额外温度偏移
    language_verbosity: float = 1.0          # > 1.0 = 更长回复

    # ── 元数据 ──
    source_valence: float = 0.0
    source_arousal: float = 0.0
    mood_label: str = "平稳"


def compute_modulation(emotional_state) -> ModuleParams:
    """从情感状态计算各模块的调制参数.

    这是 Limbic System 的核心函数——将原始情绪信号转化为
    各模块可以消费的行为参数。

    映射逻辑（心理学启发）：
    - 高唤醒（excited/anxious）→ 审查更严、规划更大胆、更爱探索
    - 低唤醒（calm/low）→ 审查宽松、规划保守、少探索
    - 高 valence（happy）→ 风险容忍度正常、语言更积极
    - 低 valence（sad/angry）→ 风险容忍度降低、语言更克制
    """

    v = emotional_state.valence   # [-1.0, 1.0]
    a = emotional_state.arousal   # [0.0, 1.0]
    mood = emotional_state.mood_label

    params = ModuleParams(
        source_valence=v,
        source_arousal=a,
        mood_label=mood,
    )

    # ── 审查模块 ──
    # 高唤醒 → 更严格的审查（vigilance increases with arousal）
    # 高 |valence| → 情绪强度越高，越在意原则对齐
    emotional_intensity = abs(v)
    params.review_strictness = 1.0 + a * 0.3 + emotional_intensity * 0.15
    # 范围: [1.0, 1.45] — 最高 +45% 严格度
    params.review_confidence_bias = a * 0.05  # arousal 带来额外信心

    # ── 记忆模块 ──
    # 高 |valence| → 情绪强度越高，记忆权重越大
    params.memory_emotional_boost = 1.0 + emotional_intensity * 0.3
    # 范围: [1.0, 1.3]
    # 高 arousal → 检索更多记忆（alert state → broader recall）
    params.memory_recall_depth = 15 + int(a * 15)  # [15, 30]

    # ── 规划模块 ──
    # 高 arousal → 大胆规划（excited → ambitious plans）
    # 低 valence + 高 arousal (anxious) → 保守规划（anxiety → caution）
    if v < -0.2 and a > 0.5:
        # 焦虑状态: 更保守
        params.planning_aggressiveness = 0.7
        params.planning_max_steps = 3
    elif a > 0.6:
        # 兴奋状态: 更大胆
        params.planning_aggressiveness = 1.3
        params.planning_max_steps = 7
    else:
        params.planning_aggressiveness = 1.0 + a * 0.2
        params.planning_max_steps = 5

    # ── 工具模块 ──
    # 低 valence → 减少危险工具使用（sad/angry → risk averse）
    if v < -0.3:
        params.tool_risk_tolerance = 0.3  # 极大减少危险工具
    elif v < 0.0:
        params.tool_risk_tolerance = 0.7
    else:
        params.tool_risk_tolerance = 1.0

    # 高 arousal + 高 valence → 好奇心旺盛
    params.tool_curiosity = 1.0 + max(0, v) * 0.3 + a * 0.2
    # 范围: [1.0, 1.5]

    # ── 语言模块 ──
    # 高 arousal → 更高温度（更多样化）
    params.language_temperature_bias = a * 0.05
    # 高 valence → 更愿意多说（positive → verbose）
    params.language_verbosity = 1.0 + max(0, v) * 0.3

    return params


def modulate_review_threshold(base_threshold: float, params: ModuleParams) -> float:
    """根据情绪调制审查通过阈值."""
    # strictness > 1.0 → 阈值降低（更难通过）
    adjusted = base_threshold / params.review_strictness
    return max(0.3, min(0.95, adjusted))


def modulate_planning_steps(base_max: int, params: ModuleParams) -> int:
    """根据情绪调制规划步骤上限."""
    return max(1, min(params.planning_max_steps, max(1, base_max)))


def modulate_tool_danger(default_dangerous: bool, params: ModuleParams) -> bool:
    """根据情绪调制工具危险判断."""
    if not default_dangerous:
        return False
    # 风险容忍度低时，非必要危险工具被抑制
    if params.tool_risk_tolerance < 0.5:
        return True  # 仍然标记危险，但会触发额外确认
    return True
