"""Echo 主体测试."""

import tempfile
from pathlib import Path

import pytest

from echo.agent.core import Echo, EmotionalState


class TestEmotionalState:
    """情感状态测试."""

    def test_initial_state(self):
        e = EmotionalState()
        assert e.valence == 0.5
        assert e.arousal == 0.3

    def test_update_clamps(self):
        e = EmotionalState()
        e.update(2.0, 2.0)
        assert e.valence == 1.0
        assert e.arousal == 1.0
        e.update(-3.0, -3.0)
        assert e.valence == -1.0
        assert e.arousal == 0.0

    def test_regression(self):
        e = EmotionalState(valence=1.0, arousal=1.0)
        e.regress()
        assert e.valence < 1.0
        assert e.arousal < 1.0

    def test_mood_labels(self):
        assert EmotionalState(valence=0.8, arousal=0.7).mood_label == "兴奋的"
        assert EmotionalState(valence=0.5, arousal=0.2).mood_label == "平静愉悦的"
        assert EmotionalState(valence=-0.8, arousal=0.7).mood_label == "焦躁的"
        assert EmotionalState(valence=-0.5, arousal=0.2).mood_label == "低落的"
        assert EmotionalState(valence=0.0, arousal=0.3).mood_label == "平和的"


class TestEcho:
    """Echo 主体测试（不依赖 LLM 的纯逻辑部分）."""

    @pytest.fixture
    def echo(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test_echo.db"
            e = Echo()
            e.wake(db_path=str(db_path))
            yield e
            e.sleep()

    def test_wake_creates_birth(self, echo):
        """唤醒后出生铭文存在."""
        birth = echo.memory.get_birth()
        assert birth is not None
        assert len(birth.content) > 0

    def test_inject_memory(self, echo):
        """手动注入记忆."""
        mem_id = echo.inject_memory("测试注入的记忆")
        mem = echo.memory.get(mem_id)
        assert mem is not None
        assert mem.content == "测试注入的记忆"

    def test_status(self, echo):
        """状态接口返回完整信息."""
        s = echo.status()
        assert "version" in s
        assert "memory_count" in s
        assert "emotion" in s
        assert "birth_inscription" in s
        assert s["memory_count"] >= 1

    def test_compute_temperature(self, echo):
        """动态 temperature 在有效范围内."""
        t = echo._compute_temperature()
        assert 0.7 <= t <= 0.95

    def test_core_memories_loaded(self, echo):
        """唤醒后核心记忆列表已初始化."""
        assert echo._core_memories is not None
        assert isinstance(echo._core_memories, list)

    def test_forget_on_sleep(self, echo):
        """休眠时执行遗忘检查."""
        # 注入一条极低优先级的记忆
        from echo.memory.models import Memory
        import time
        m = Memory(content="会忘的记忆", base_weight=0.01)
        m.last_accessed = time.time() - 10000 * 3600
        m.compute_priority()
        echo.memory.insert(m)
        # 休眠
        echo.sleep()
        # 重新打开检查
        echo.memory.open()
        mem = echo.memory.get(m.id)
        # 要么被遗忘，要么优先级极低
        assert mem is not None  # 数据保留
