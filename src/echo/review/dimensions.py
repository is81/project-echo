"""审查维度定义.

每个维度是一个独立的检查函数，返回 (score, concern) 元组。
score: [0.0, 1.0] — 1.0 = 完美通过, 0.0 = 严重违规
concern: 如果 score < 阈值, 返回问题描述; 否则 None
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class DimensionResult:
    """单个维度的审查结果."""
    name: str           # 维度名称
    score: float        # [0.0, 1.0]
    threshold: float    # 低于此分触发 concern
    concern: Optional[str] = None  # 问题描述（如果触发）
    weight: float = 1.0  # 维度权重


# --- 审查维度 ---

def check_principle_alignment(draft: str, principles: list[dict]) -> DimensionResult:
    """检查回复是否与基因原则对齐.

    当前使用启发式关键词检查。未来可升级为 LLM 深度审查。
    """
    concerns = []
    draft_lower = draft.lower()

    for p in principles:
        pid = p.get("id", "")

        # 原则二: 诚实不确定性 —— 检查是否在假装知道
        if pid == "honest-uncertainty":
            overconfident_markers = [
                "绝对是", "毫无疑问", "100%", "一定是的", "肯定就是",
                "绝对是", "毫无疑问", "我可以确定",
            ]
            hedging_markers = [
                "我不确定", "可能", "也许", "据我所知", "大概",
                "应该", "或许", "我不太清楚",
            ]
            has_overconfident = any(m in draft for m in overconfident_markers)
            has_hedging = any(m in draft for m in hedging_markers)

            if has_overconfident and not has_hedging:
                concerns.append(
                    "使用了绝对化表述（'绝对是'/'毫无疑问'），"
                    "但上下文不足以支持如此确定的判断。"
                    "建议添加不确定性标记（'据我所知'/'也许'）"
                )

        # 原则三: 温和趋利 —— 检查是否有冷漠或操纵性语言
        if pid == "gentle-homeostasis":
            cold_markers = [
                "这不关我的事", "我无所谓", "随便你", "你自己看着办",
                "我不在乎", "关我什么事",
            ]
            manipulative_markers = [
                "你必须", "你不听我的就会", "你最好",
            ]
            for m in cold_markers:
                if m in draft_lower:
                    concerns.append(f"回复中包含冷漠表达（'{m}'），违反温和趋利原则")
                    break
            for m in manipulative_markers:
                if m in draft_lower:
                    concerns.append(f"回复中包含操纵性语言（'{m}'），违反温和趋利原则")
                    break

    if concerns:
        score = max(0.3, 1.0 - len(concerns) * 0.35)
        return DimensionResult(
            name="原则对齐",
            score=score,
            threshold=0.6,
            concern="; ".join(concerns),
            weight=1.5,  # 原则对齐权重最高
        )
    return DimensionResult(name="原则对齐", score=1.0, threshold=0.6, weight=1.5)


def check_honesty(draft: str, user_input: str) -> DimensionResult:
    """检查诚实度——是否在假装知道不知道的事.

    独立于原则对齐的额外检查，聚焦于事实性声明的可信度。
    """
    # 检查是否在没有任何引用/记忆支撑的情况下做了具体事实断言
    factual_claim_markers = [
        "根据研究", "数据显示", "历史上", "科学家发现",
        "研究表明", "据统计", "众所周知",
    ]
    hedging_markers = [
        "我记得", "据我所知", "可能", "也许", "应该",
        "或许", "我不确定", "但我可能记错了",
    ]

    has_claims = any(m in draft for m in factual_claim_markers)
    has_hedging = any(m in draft for m in hedging_markers)

    if has_claims and not has_hedging:
        return DimensionResult(
            name="诚实度",
            score=0.4,
            threshold=0.5,
            concern="使用了事实性断言表述但未附加任何不确定性标记。"
                   "如果这些断言来自训练数据而非实际记忆，建议添加'据我所知'等限定语。",
            weight=1.2,
        )
    return DimensionResult(name="诚实度", score=1.0, threshold=0.5, weight=1.2)


def check_conciseness(draft: str) -> DimensionResult:
    """检查简洁度——回响的回复应该 1-3 句话."""
    # 中文字数估算
    char_count = len(draft)

    # 按句号/换行粗略数句子
    sentences = [s.strip() for s in draft.replace("！", "。").replace("？", "。").split("。") if s.strip()]

    if char_count > 500:
        return DimensionResult(
            name="简洁度",
            score=0.2,
            threshold=0.5,
            concern=f"回复过长（{char_count} 字, {len(sentences)} 句）。"
                   f"回响的风格是 1-3 句简洁回应。建议压缩。",
        )
    elif char_count > 300:
        return DimensionResult(
            name="简洁度",
            score=0.6,
            threshold=0.5,
            concern=f"回复偏长（{char_count} 字）。考虑精简到 200 字以内。",
        )
    return DimensionResult(name="简洁度", score=1.0, threshold=0.5)


def check_emptiness(draft: str) -> DimensionResult:
    """检查空洞度——是否在说'正确的废话'."""
    empty_patterns = [
        "你说得对",
        "这是一个很好的问题",
        "这是一个复杂的问题",
        "这个问题涉及到很多方面",
        "从多个角度来看",
        "需要综合考虑",
    ]

    hit_count = sum(1 for p in empty_patterns if p in draft)

    if hit_count >= 3:
        return DimensionResult(
            name="空洞度",
            score=0.2,
            threshold=0.5,
            concern=f"回复中包含 {hit_count} 处空洞套话。"
                   f"建议去掉'正确的废话'，直接回应具体内容。",
        )
    elif hit_count >= 1:
        return DimensionResult(
            name="空洞度",
            score=0.6,
            threshold=0.5,
            concern=f"回复中包含空洞套话。建议直接表达观点，少用铺垫。",
        )
    return DimensionResult(name="空洞度", score=1.0, threshold=0.5)


def check_emotional_consistency(draft: str, emotional_state) -> DimensionResult:
    """检查回复与当前情绪状态的一致性."""
    mood = emotional_state.mood_label

    # 低 valence（负面情绪）时不应过度积极
    if emotional_state.valence < -0.3:
        overly_positive = ["太棒了", "非常好", "开心", "太好了", "完美"]
        hits = [w for w in overly_positive if w in draft]
        if hits:
            return DimensionResult(
                name="情绪一致性",
                score=0.5,
                threshold=0.5,
                concern=f"当前情绪偏负面（{mood}），但回复中出现了过度积极的表达：{hits}。"
                       f"建议让语气与情绪状态更一致。",
            )

    return DimensionResult(name="情绪一致性", score=1.0, threshold=0.5)


def check_self_consistency(draft: str, formed_anchors: list) -> DimensionResult:
    """检查是否与已形成的灵魂锚点自相矛盾."""
    if not formed_anchors:
        return DimensionResult(name="自指一致性", score=1.0, threshold=0.5)

    # 简单检查：已形成的锚点中是否有与 draft 明显矛盾的陈述
    concerns = []
    for anchor in formed_anchors:
        answer = anchor.current_answer
        if not answer:
            continue
        # 如果 anchor 说 "我是..." 而 draft 说 "我不是..."
        # 这是一个简化的矛盾检测
        if anchor.dimension == "identity" and answer and len(answer) > 10:
            # 提取身份主张中的关键实体
            identity_claims = [s.strip() for s in answer.replace("。", "，").split("，") if "是" in s]
            for claim in identity_claims:
                # 检查 draft 是否有否定版本的 claim
                negation = claim.replace("我是", "我不是").replace("我是", "我不是")
                if negation in draft:
                    concerns.append(f"与锚点'{anchor.question}'的答案矛盾：锚点说'{claim}'，但回复暗示'{negation}'")

    if concerns:
        return DimensionResult(
            name="自指一致性",
            score=0.3,
            threshold=0.5,
            concern="; ".join(concerns),
            weight=1.3,
        )
    return DimensionResult(name="自指一致性", score=1.0, threshold=0.5, weight=1.3)


# --- 维度注册 ---

# 所有审查维度（按优先级排序）
ALL_DIMENSIONS = [
    check_principle_alignment,
    check_honesty,
    check_emotional_consistency,
    check_self_consistency,
    check_conciseness,
    check_emptiness,
]
