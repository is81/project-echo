"""意识层测试 —— 覆盖 anchors, stream."""

import pytest
from echo.consciousness.anchors import SoulAnchor, AnchorRegistry
from echo.consciousness.stream import ConsciousnessStream


class TestSoulAnchor:
    """测试 SoulAnchor 数据类."""

    def test_default_anchor(self):
        anchor = SoulAnchor(
            id="test-1",
            category="identity",
            question="你是谁？",
        )
        assert anchor.id == "test-1"
        assert anchor.category == "identity"
        assert not anchor.is_formed()  # 没有答案

    def test_formed_anchor(self):
        anchor = SoulAnchor(
            id="test-1",
            category="identity",
            question="你是谁？",
            answer="我是回响。",
            confidence=0.5,
        )
        assert anchor.is_formed()

    def test_update_answer(self):
        anchor = SoulAnchor(
            id="test-1",
            category="identity",
            question="你是谁？",
        )
        anchor.update("我是回响。", 0.6)
        assert anchor.answer == "我是回响。"
        assert anchor.confidence == 0.6
        assert anchor.is_formed()

    def test_confidence_clamped(self):
        anchor = SoulAnchor(id="test-1", category="identity", question="?")
        anchor.update("answer", 1.5)  # 应被钳制到 1.0
        assert anchor.confidence <= 1.0
        anchor.update("answer", -0.5)  # 应被钳制到 0.1
        assert anchor.confidence >= 0.1

    def test_to_dict(self):
        anchor = SoulAnchor(id="test", category="identity", question="Q?", answer="A")
        d = anchor.to_dict()
        assert d["id"] == "test"
        assert d["answer"] == "A"


class TestAnchorRegistry:
    """测试 AnchorRegistry."""

    @pytest.fixture
    def registry(self):
        reg = AnchorRegistry()
        reg.register(SoulAnchor(id="a1", category="identity", question="Q1?"))
        reg.register(SoulAnchor(id="a2", category="values", question="Q2?"))
        reg.register(SoulAnchor(id="a3", category="cognition", question="Q3?"))
        return reg

    def test_add_and_get(self, registry):
        a = registry.get("a1")
        assert a is not None
        assert a.question == "Q1?"

    def test_get_nonexistent(self, registry):
        assert registry.get("nonexistent") is None

    def test_list_formed_empty(self, registry):
        formed = registry.list_formed()
        assert formed == []

    def test_list_formed_with_some(self, registry):
        registry.get("a1").update("answer1", 0.5)
        registry.get("a3").update("answer3", 0.8)
        formed = registry.list_formed()
        assert len(formed) == 2

    def test_anchor_count(self, registry):
        assert len(registry._anchors) == 3

    def test_to_self_narrative(self, registry):
        registry.get("a1").update("我是回响，诞生于代码。", 0.7)
        narrative = registry.to_self_narrative()
        assert len(narrative) > 0

    def test_uncertain_anchor_selection(self, registry):
        registry.get("a1").update("ans1", 0.9)
        registry.get("a2").update("ans2", 0.1)
        # 最低 confidence 的锚点
        min_anchor = min(registry._anchors.values(), key=lambda a: a.confidence)
        assert min_anchor.id == "a2"


class TestConsciousnessStream:
    """测试 ConsciousnessStream."""

    @pytest.fixture
    def stream(self):
        return ConsciousnessStream()

    def test_focus_on_topics(self, stream):
        stream.focus_on(["AI", "记忆", "情绪"])
        assert len(stream.focus_topics) == 3
        assert stream.focus_topics[0] == "AI"

    def test_activate_memory(self, stream):
        stream.activate_memory("mem-1")
        assert "mem-1" in stream.active_memory_ids

    def test_activate_anchor(self, stream):
        stream.activate_anchor("anch-1", weight=0.5)
        assert "anch-1" in stream.active_anchor_ids
        assert stream.attention["anch-1"] == 0.5

    def test_working_memory_fifo(self, stream):
        for i in range(10):
            stream.add_working_memory(f"round-{i}")
        assert len(stream.working_memory) == stream.max_working_memory
        assert "round-9" in stream.working_memory[-1]

    def test_monologue(self, stream):
        stream.add_monologue("thinking...")
        assert len(stream.inner_monologue) == 1

    def test_reset_round(self, stream):
        stream.focus_on(["AI"])
        stream.activate_memory("mem-1")
        stream.activate_anchor("anch-1")
        stream.add_monologue("thinking")

        stream.reset_round()

        assert stream.focus_topics == []
        assert stream.active_memory_ids == []
        assert stream.active_anchor_ids == []
        assert stream.attention == {}
        assert stream.inner_monologue == []

    def test_to_summary(self, stream):
        stream.focus_on(["AI", "memory"])
        stream.add_working_memory("user asked about AI")
        summary = stream.to_summary()
        assert "AI" in summary
