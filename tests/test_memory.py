"""记忆系统测试 — 优先级评分 + 半衰期衰减 + 主动遗忘."""

import tempfile
import time
from pathlib import Path

import pytest

from echo.memory.models import (
    Memory, DEFAULT_HALF_LIFE_HOURS, FORGET_THRESHOLD,
)
from echo.memory.priority import (
    score_memory, score_batch, forget_check, select_core_memories,
)
from echo.memory.store import MemoryStore


class TestMemoryModel:
    """Memory 数据模型测试."""

    def test_create_birth(self):
        """出生铭文永不衰减、半衰期为 0."""
        m = Memory.create_birth("我是回响。")
        assert m.source == "birth"
        assert m.half_life_hours == 0.0
        assert m.base_weight == 1.0
        assert m.priority_score == 1.0
        # 不衰减
        m.apply_half_life(10000)
        assert m.base_weight == 1.0

    def test_record_access(self):
        """访问记录提升权重."""
        m = Memory(content="测试记忆", base_weight=0.5)
        m.record_access()
        assert m.base_weight == 0.52  # 0.5 + 0.02
        assert m.access_count == 1

    def test_weight_cap(self):
        """权重不超过 1.0."""
        m = Memory(content="测试", base_weight=0.99)
        m.record_access()
        m.record_access()
        assert m.base_weight == 1.0

    def test_half_life_decay(self):
        """半衰期衰减：7天后权重减半."""
        m = Memory(content="普通记忆", base_weight=1.0,
                   half_life_hours=168.0)
        m.apply_half_life(168)  # 恰好 7 天
        assert m.base_weight == pytest.approx(0.5, rel=0.01)

    def test_half_life_decay_double(self):
        """14天后权重降至 0.25."""
        m = Memory(content="旧记忆", base_weight=1.0,
                   half_life_hours=168.0)
        m.apply_half_life(336)  # 14 天 = 2 个半衰期
        assert m.base_weight == pytest.approx(0.25, rel=0.01)

    def test_high_arousal_slower_decay(self):
        """高唤醒度记忆半衰期翻倍."""
        m = Memory(content="激动人心的记忆",
                   base_weight=1.0, half_life_hours=168.0,
                   emotional_arousal=0.8)
        m.apply_half_life(168)
        # 高唤醒 → 半衰期变为 336h，所以 168h 后权重 > 0.5
        assert m.base_weight > 0.5

    def test_priority_score_computation(self):
        """优先级评分计算."""
        m = Memory(content="重要记忆", base_weight=1.0,
                   access_count=5, emotional_valence=0.8,
                   emotional_arousal=0.7)
        m.last_accessed = time.time()  # 刚刚访问过
        score = m.compute_priority()
        assert score > 1.0  # 高权重 + 情感 + 刚访问

    def test_priority_score_stale(self):
        """旧记忆优先级低."""
        m = Memory(content="旧记忆", base_weight=1.0)
        m.last_accessed = time.time() - 500 * 3600  # 500 小时前
        score = m.compute_priority()
        assert score < 0.3  # 很旧了

    def test_check_forget(self):
        """优先级过低时自动标记遗忘."""
        m = Memory(content="快忘掉的记忆", base_weight=0.03)
        m.last_accessed = time.time() - 1000 * 3600
        assert m.check_forget() is True
        assert m.forgotten is True

    def test_birth_never_forgotten(self):
        """出生铭文永不被遗忘."""
        m = Memory.create_birth("根")
        assert m.check_forget() is False

    def test_serialize_roundtrip(self):
        """序列化往返."""
        m = Memory(content="测试", tags=["a", "b"],
                   emotional_valence=0.5, priority_score=0.8,
                   half_life_hours=200)
        data = m.to_dict()
        m2 = Memory.from_dict(data)
        assert m2.content == m.content
        assert m2.priority_score == 0.8
        assert m2.half_life_hours == 200
        assert m2.forgotten is False


class TestPriority:
    """优先级评分引擎测试."""

    def test_score_batch_sorts(self):
        """批量评分按优先级降序."""
        m1 = Memory(content="高优", base_weight=1.0, access_count=10)
        m1.last_accessed = time.time()
        m2 = Memory(content="低优", base_weight=0.2, access_count=0)
        m2.last_accessed = time.time() - 10000 * 3600
        scored = score_batch([m2, m1])
        assert scored[0][0].content == "高优"
        assert scored[1][0].content == "低优"

    def test_forget_check_splits(self):
        """遗忘检查正确分组."""
        m1 = Memory(content="高优", base_weight=0.8)
        m1.last_accessed = time.time()
        m2 = Memory(content="极低", base_weight=0.01)
        m2.last_accessed = time.time() - 10000 * 3600
        kept, forgotten = forget_check([m1, m2])
        assert len(kept) >= 1
        assert len(forgotten) >= 1
        assert forgotten[0].forgotten is True

    def test_select_core_memories(self):
        """选出核心记忆."""
        mems = []
        for i in range(10):
            m = Memory(content=f"记忆{i}", base_weight=0.3 + i * 0.07)
            m.last_accessed = time.time()
            m.compute_priority()
            mems.append(m)
        core = select_core_memories(mems, top_n=3, min_score=0.1)
        assert len(core) <= 3
        # 最高优先级排第一
        assert core[0].priority_score >= core[-1].priority_score


class TestMemoryStore:
    """MemoryStore 新功能测试."""

    @pytest.fixture
    def store(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            s = MemoryStore(db_path)
            s.open()
            yield s
            s.close()

    def test_insert_and_get(self, store):
        m = Memory(content="Hello", tags=["greeting"])
        store.insert(m)
        retrieved = store.get(m.id)
        assert retrieved is not None
        assert retrieved.content == "Hello"
        assert retrieved.priority_score > 0

    def test_birth_persistence(self, store):
        birth = Memory.create_birth("我在。")
        store.insert(birth)
        found = store.get_birth()
        assert found is not None
        assert found.content == "我在。"

    def test_half_life_decay_batch(self, store):
        """批量半衰期衰减."""
        for i in range(5):
            m = Memory(content=f"记忆{i}", base_weight=0.8,
                       half_life_hours=168)
            m.last_accessed = time.time() - 200 * 3600
            store.insert(m)
        affected = store.apply_half_life(168)
        assert affected > 0
        # 验证权重已降低
        mem = store.get(store.list_active(limit=1)[0].id)
        assert mem.base_weight < 0.8

    def test_forget_low_priority(self, store):
        """主动遗忘低优先级记忆."""
        m = Memory(content="极低优", base_weight=0.01)
        m.last_accessed = time.time() - 10000 * 3600
        m.compute_priority()
        store.insert(m)
        count = store.forget_low_priority(threshold=FORGET_THRESHOLD)
        # 应该被遗忘（如果优先级够低）
        retrieved = store.get(m.id)
        assert retrieved is not None  # 仍然存在
        # 但不再出现在 list_active 中
        active_ids = {m.id for m in store.list_active()}
        if retrieved.priority_score < FORGET_THRESHOLD:
            assert m.id not in active_ids

    def test_get_core_memories(self, store):
        """获取核心记忆."""
        for i in range(10):
            m = Memory(content=f"重要记忆{i}", base_weight=0.6 + i * 0.03)
            m.last_accessed = time.time()
            m.compute_priority()
            store.insert(m)
        core = store.get_core_memories(n=4)
        assert len(core) <= 4
        # 按优先级降序
        for i in range(len(core) - 1):
            assert core[i].priority_score >= core[i + 1].priority_score

    def test_get_old_details(self, store):
        """获取旧细节记忆用于压缩."""
        now = time.time()
        # 一条旧记忆
        old = Memory(content="旧记忆", base_weight=0.2)
        old.created_at = now - 50 * 3600  # 50 小时前
        old.compute_priority()
        store.insert(old)
        # 一条新记忆
        fresh = Memory(content="新记忆", base_weight=0.9)
        fresh.created_at = now
        fresh.compute_priority()
        store.insert(fresh)

        old_mems = store.get_old_details(age_hours=24, max_weight=0.3)
        old_ids = {m.id for m in old_mems}
        assert old.id in old_ids
        assert fresh.id not in old_ids

    def test_count(self, store):
        assert store.count() == 0
        store.insert(Memory(content="1"))
        assert store.count() == 1
        store.insert(Memory(content="2"))
        assert store.count() == 2
