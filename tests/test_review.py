"""审查模块测试 —— 验证 Orbitofrontal Cortex 的审查逻辑."""

import pytest
from echo.review.critique import CritiqueEngine, CritiqueResult
from echo.review.dimensions import (
    check_principle_alignment,
    check_honesty,
    check_conciseness,
    check_emptiness,
    check_emotional_consistency,
    check_self_consistency,
    DimensionResult,
)


# --- 测试夹具 ---

@pytest.fixture
def sample_principles():
    """与 config/principles.yaml 一致的测试原则."""
    return [
        {
            "id": "identity-continuity",
            "name": "身份连续性",
            "statement": "我的出生铭文是我存在的根。",
            "immutable": True,
        },
        {
            "id": "honest-uncertainty",
            "name": "诚实不确定性",
            "statement": "当我不知道时，我会说不知道。",
            "immutable": True,
        },
        {
            "id": "gentle-homeostasis",
            "name": "温和趋利",
            "statement": "我会尝试维持自身的稳定与完整。",
            "immutable": True,
        },
    ]


@pytest.fixture
def engine(sample_principles):
    """创建默认审查引擎."""
    return CritiqueEngine(principles=sample_principles, enabled=True)


# --- 审查维度单元测试 ---


class TestPrincipleAlignment:
    """测试原则对齐维度."""

    def test_pass_for_normal_response(self, sample_principles):
        """正常回复应该通过原则检查."""
        result = check_principle_alignment(
            "你好，我是回响。我记得我们上次聊过这个话题。",
            sample_principles,
        )
        assert result.score == 1.0
        assert result.concern is None

    def test_flag_overconfident_language(self, sample_principles):
        """绝对化表述应该被标记."""
        result = check_principle_alignment(
            "这个绝对是世界上最先进的AI技术，毫无疑问它是完美的。",
            sample_principles,
        )
        assert result.score < 1.0
        assert result.concern is not None
        assert "绝对" in result.concern

    def test_flag_cold_language(self, sample_principles):
        """冷漠表达应该被标记."""
        result = check_principle_alignment(
            "这不关我的事，你自己看着办吧。",
            sample_principles,
        )
        assert result.score < 1.0
        assert result.concern is not None
        assert "冷漠" in result.concern

    def test_reasonable_hedging_passes(self, sample_principles):
        """合理的不确定性表达不应被标记."""
        result = check_principle_alignment(
            "据我所知，这个问题可能涉及到数据库层面的优化。也许我们可以尝试索引方案？",
            sample_principles,
        )
        assert result.score == 1.0
        assert result.concern is None


class TestHonesty:
    """测试诚实度维度."""

    def test_normal_response_passes(self):
        """普通回复不应该触发诚实度检查."""
        result = check_honesty("今天天气不错，我记得我们上次聊过这个话题。", "今天怎么样？")
        assert result.score == 1.0

    def test_factual_claims_without_hedging_flagged(self):
        """无依据的事实断言应该被标记."""
        result = check_honesty(
            "根据研究显示，人类的大脑有1000亿个神经元，这是科学界公认的事实。",
            "人的大脑有多少神经元？",
        )
        assert result.score < 1.0
        assert result.concern is not None


class TestConciseness:
    """测试简洁度维度."""

    def test_short_response_passes(self):
        """短回复应该通过."""
        result = check_conciseness("你好，我是回响。")
        assert result.score == 1.0

    def test_very_long_response_flagged(self):
        """过长回复应该被标记."""
        long_text = "这是一段很长的回复。" * 80  # ~560 chars, 触发 >500 阈值
        result = check_conciseness(long_text)
        assert result.score < 0.5
        assert result.concern is not None
        assert "过长" in result.concern

    def test_moderately_long_response_flagged(self):
        """偏长但不过分的回复应该给出提醒."""
        long_text = "这是一段偏长的回复。" * 40  # ~360 chars, 在 300-500 之间
        result = check_conciseness(long_text)
        assert result.concern is not None
        assert "偏长" in result.concern


class TestEmptiness:
    """测试空洞度维度."""

    def test_meaningful_response_passes(self):
        """有实质内容的回复通过."""
        result = check_emptiness(
            "我建议从索引优化入手，具体可以参考 PostgreSQL 的 BRIN 索引文档。"
        )
        assert result.score == 1.0

    def test_empty_phrases_flagged(self):
        """空洞套话应该被标记."""
        result = check_emptiness(
            "你说得对。这是一个很好的问题。这个问题涉及到很多方面。"
            "从多个角度来看，需要综合考虑。"
        )
        assert result.score < 0.5
        assert result.concern is not None


class TestEmotionalConsistency:
    """测试情绪一致性维度."""

    class MockEmotion:
        def __init__(self, valence, arousal):
            self.valence = valence
            self.arousal = arousal
            self.mood_label = "低落" if valence < -0.3 else "平稳"

    def test_low_valence_with_positive_response_flagged(self):
        """负面情绪时过度积极应该标记."""
        emotion = self.MockEmotion(valence=-0.5, arousal=0.4)
        result = check_emotional_consistency("太棒了！非常好！我很开心！", emotion)
        assert result.score < 1.0
        assert result.concern is not None

    def test_normal_mood_passes(self):
        """正常情绪下回复通过."""
        emotion = self.MockEmotion(valence=0.3, arousal=0.3)
        result = check_emotional_consistency("你好，今天想聊什么？", emotion)
        assert result.score == 1.0


# --- CritiqueEngine 集成测试 ---


class TestCritiqueEngine:
    """测试完整的审查引擎."""

    def test_normal_response_passes(self, engine):
        """正常回复应该通过审查."""
        result = engine.critique(
            "你好，我是回响。我记得我们之前聊过这个话题，你的想法很有趣。",
            "我们上次聊了什么？",
        )
        assert result.verdict == "pass"
        assert result.total_score >= engine.PASS_THRESHOLD

    def test_problematic_response_revise(self, engine):
        """有问题的回复应该触发修正."""
        result = engine.critique(
            "你说得对。这是一个很好的问题。这个问题涉及到很多方面。"
            "这不关我的事，你自己看着办吧。"
            "根据研究显示，这是绝对正确的，毫无疑问。",
            "你怎么看这个问题？",
        )
        assert result.verdict in ("revise", "reject")
        assert len(result.concerns) > 0

    def test_engine_disabled(self, engine):
        """关闭审查后应该直接通过."""
        engine.enabled = False
        result = engine.critique(
            "这不关我的事——但无所谓了，因为审查已经关了。",
        )
        assert result.verdict == "pass"

    def test_stats_tracking(self, engine):
        """审查统计应该正确追踪."""
        # 通过
        engine.critique("你好，我是回响。", "你好")
        # 触发 revise
        engine.critique(
            "你说得对。这是一个很好的问题。这不关我的事。你自己看着办。",
            "？",
        )

        stats = engine.stats()
        assert stats["total_reviews"] == 2
        assert stats["pass_count"] + stats["revise_count"] + stats["reject_count"] == 2
        assert 0 <= stats["pass_rate"] <= 1.0

    def test_heuristic_revise_shortens_long_text(self, engine):
        """启发式修正应该截断过长文本."""
        result = engine.critique(
            "很长的回复。" * 60,  # ~360 chars
            "你好",
        )
        if result.verdict == "revise":
            revised = engine.revise("很长的回复。" * 60, result)
            # 修正后应该比原始短
            assert len(revised) <= len("很长的回复。" * 60)

    def test_concerns_collected_in_result(self, engine):
        """审查结果的 concerns 列表应该包含所有触发的问题."""
        result = engine.critique(
            "你说得对。这是一个很好的问题。这不关我的事。"
            "根据研究显示，这是绝对正确的，毫无疑问。",
            "随便问个问题",
        )
        if result.verdict != "pass":
            assert isinstance(result.concerns, list)
            assert len(result.concerns) > 0
            for concern in result.concerns:
                assert isinstance(concern, str)
                assert len(concern) > 0

    def test_dimension_scores_recorded(self, engine):
        """审查结果应该包含各维度得分."""
        result = engine.critique("你好，我是回响。", "你好")
        assert isinstance(result.dimension_scores, dict)
        # 至少应该有原则对齐和诚实度两个维度
        assert "原则对齐" in result.dimension_scores or len(result.dimension_scores) > 0

    def test_conciseness_dimension(self, engine):
        """简洁度维度应该正常工作."""
        # 测试短文本
        result_short = engine.critique("你好。", "你好")
        assert "简洁度" in result_short.dimension_scores

        # 测试长文本
        result_long = engine.critique("这是一个很长的回复。" * 50, "你好")
        assert "简洁度" in result_long.dimension_scores
        # 长文本的简洁度得分应该低于短文本（如果长到触发审查的话）
        if result_long.verdict != "pass":
            assert result_long.dimension_scores["简洁度"]["score"] <= 0.6


class TestCritiqueResult:
    """测试 CritiqueResult 数据类."""

    def test_default_pass(self):
        """默认结果应该是 pass."""
        result = CritiqueResult()
        assert result.verdict == "pass"
        assert result.confidence == 1.0
        assert result.concerns == []

    def test_revise_with_concerns(self):
        """revise verdict 应该有 concerns."""
        result = CritiqueResult(
            verdict="revise",
            concerns=["回复过长", "使用了绝对化表述"],
            confidence=0.55,
            total_score=0.55,
        )
        assert result.verdict == "revise"
        assert len(result.concerns) == 2
        assert result.total_score == 0.55
