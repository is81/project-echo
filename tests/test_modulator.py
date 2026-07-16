"""情绪调制器测试 —— 验证 Limbic System 跨模块权重偏移."""

import pytest
from echo.consciousness.modulator import (
    ModuleParams,
    compute_modulation,
    modulate_review_threshold,
    modulate_planning_steps,
    modulate_tool_danger,
)


class MockEmotion:
    """模拟 EmotionalState."""
    def __init__(self, valence, arousal):
        self.valence = valence
        self.arousal = arousal

    @property
    def mood_label(self):
        if self.valence > 0.3 and self.arousal > 0.5:
            return "兴奋"
        elif self.valence > 0.3:
            return "平稳"
        elif self.valence < -0.3 and self.arousal > 0.5:
            return "焦虑"
        elif self.valence < -0.3:
            return "低落"
        elif self.arousal > 0.5:
            return "警觉"
        else:
            return "平静"


class TestModuleParams:
    """测试 ModuleParams 数据类."""

    def test_default_params_neutral(self):
        """默认参数应该全部是中性值."""
        params = ModuleParams()
        assert params.review_strictness == 1.0
        assert params.memory_emotional_boost == 1.0
        assert params.planning_aggressiveness == 1.0
        assert params.tool_risk_tolerance == 1.0
        assert params.language_temperature_bias == 0.0
        assert params.language_verbosity == 1.0

    def test_params_store_source_emotion(self):
        """应该记录源情绪信息."""
        params = ModuleParams(source_valence=0.5, source_arousal=0.3, mood_label="平稳")
        assert params.source_valence == 0.5
        assert params.source_arousal == 0.3
        assert params.mood_label == "平稳"


class TestComputeModulation:
    """测试核心调制计算."""

    def test_neutral_emotion_produces_near_neutral_params(self):
        """中性情绪产生接近中性的参数."""
        emotion = MockEmotion(valence=0.0, arousal=0.3)
        params = compute_modulation(emotion)

        # 不应有极端偏移
        assert 0.8 <= params.review_strictness <= 1.3
        assert 0.8 <= params.memory_emotional_boost <= 1.2
        assert 0.8 <= params.tool_risk_tolerance <= 1.1

    def test_high_arousal_increases_review_strictness(self):
        """高唤醒 → 审查更严格."""
        calm = MockEmotion(valence=0.2, arousal=0.1)
        excited = MockEmotion(valence=0.2, arousal=0.9)

        calm_params = compute_modulation(calm)
        excited_params = compute_modulation(excited)

        assert excited_params.review_strictness > calm_params.review_strictness

    def test_high_valence_increases_emotional_boost(self):
        """高 |valence| → 情感记忆权重更大."""
        neutral = MockEmotion(valence=0.0, arousal=0.3)
        intense = MockEmotion(valence=0.9, arousal=0.3)

        neutral_params = compute_modulation(neutral)
        intense_params = compute_modulation(intense)

        assert intense_params.memory_emotional_boost > neutral_params.memory_emotional_boost

    def test_anxiety_makes_planning_cautious(self):
        """焦虑状态 → 规划保守."""
        anxious = MockEmotion(valence=-0.5, arousal=0.8)
        params = compute_modulation(anxious)

        assert params.planning_aggressiveness < 1.0
        assert params.planning_max_steps == 3

    def test_excitement_makes_planning_aggressive(self):
        """兴奋状态 → 规划大胆."""
        excited = MockEmotion(valence=0.4, arousal=0.7)
        params = compute_modulation(excited)

        assert params.planning_aggressiveness > 1.0
        assert params.planning_max_steps >= 5

    def test_negative_valence_reduces_risk_tolerance(self):
        """负面情绪 → 减少危险工具使用."""
        happy = MockEmotion(valence=0.5, arousal=0.3)
        sad = MockEmotion(valence=-0.5, arousal=0.3)

        happy_params = compute_modulation(happy)
        sad_params = compute_modulation(sad)

        assert sad_params.tool_risk_tolerance < happy_params.tool_risk_tolerance

    def test_high_arousal_increases_language_temperature(self):
        """高唤醒 → 语言温度上升."""
        calm = MockEmotion(valence=0.3, arousal=0.1)
        alert = MockEmotion(valence=0.3, arousal=0.8)

        calm_params = compute_modulation(calm)
        alert_params = compute_modulation(alert)

        assert alert_params.language_temperature_bias > calm_params.language_temperature_bias

    def test_positive_valence_increases_verbosity(self):
        """积极情绪 → 更愿意多说."""
        neutral = MockEmotion(valence=0.0, arousal=0.3)
        happy = MockEmotion(valence=0.8, arousal=0.3)

        neutral_params = compute_modulation(neutral)
        happy_params = compute_modulation(happy)

        assert happy_params.language_verbosity > neutral_params.language_verbosity

    def test_negative_valence_does_not_increase_verbosity(self):
        """负面情绪不增加多言."""
        sad = MockEmotion(valence=-0.5, arousal=0.3)
        params = compute_modulation(sad)

        # 语言冗长度不应超过中性（负 valence 不加成）
        assert params.language_verbosity <= 1.1

    def test_all_mood_labels_work(self):
        """所有情绪标签都应该正常计算."""
        moods = [
            MockEmotion(0.5, 0.7),   # 兴奋
            MockEmotion(0.4, 0.2),   # 平稳
            MockEmotion(-0.5, 0.7),  # 焦虑
            MockEmotion(-0.4, 0.2),  # 低落
            MockEmotion(0.1, 0.7),   # 警觉
            MockEmotion(0.1, 0.2),   # 平静
        ]

        for emotion in moods:
            params = compute_modulation(emotion)
            assert params.mood_label != ""
            assert 0.3 <= params.tool_risk_tolerance <= 1.0
            assert params.planning_max_steps >= 1
            assert params.memory_recall_depth >= 10


class TestModulatorHelpers:
    """测试辅助调制函数."""

    def test_modulate_review_threshold_strictness(self):
        """审查严格度 > 1.0 → 阈值降低."""
        params = ModuleParams(review_strictness=1.3)
        adjusted = modulate_review_threshold(0.75, params)
        assert adjusted < 0.75  # 阈值降低 = 更难通过

    def test_modulate_review_threshold_floor(self):
        """审查阈值不应无限降低."""
        params = ModuleParams(review_strictness=5.0)  # 极端严格
        adjusted = modulate_review_threshold(0.75, params)
        assert adjusted >= 0.3  # 有下限

    def test_modulate_review_threshold_ceiling(self):
        """审查阈值不应超过上限."""
        params = ModuleParams(review_strictness=0.1)  # 极端宽松
        adjusted = modulate_review_threshold(0.75, params)
        assert adjusted <= 0.95

    def test_modulate_planning_steps_respects_max(self):
        """规划步骤不应超过 mood 决定的上限."""
        params = ModuleParams(planning_max_steps=3)
        result = modulate_planning_steps(10, params)
        assert result == 3

    def test_modulate_planning_steps_at_least_one(self):
        """规划步骤至少为 1."""
        params = ModuleParams(planning_max_steps=0)
        result = modulate_planning_steps(5, params)
        assert result >= 1

    def test_modulate_tool_danger_always_when_not_dangerous(self):
        """非危险工具永远不标记危险."""
        params = ModuleParams(tool_risk_tolerance=0.1)  # 极端保守
        assert not modulate_tool_danger(False, params)

    def test_modulate_tool_danger_preserves_when_dangerous(self):
        """危险工具保持危险标记."""
        params = ModuleParams(tool_risk_tolerance=0.5)
        assert modulate_tool_danger(True, params)
