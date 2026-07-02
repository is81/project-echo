"""记忆系统测试."""

import tempfile
from pathlib import Path

import pytest

from echo.memory.models import Memory
from echo.memory.store import MemoryStore


class TestMemory:
    """Memory 数据模型测试."""

    def test_create_birth(self):
        """出生铭文记忆永不衰减、不可归档."""
        m = Memory.create_birth("我是回响。")
        assert m.source == "birth"
        assert m.decay_rate == 0.0
        assert m.base_weight == 1.0
        assert "birth" in m.tags

        # 即使过了很久也不衰减
        m.apply_decay(10000)
        assert m.base_weight == 1.0

    def test_record_access(self):
        """访问记录提升权重."""
        m = Memory(content="测试记忆", base_weight=0.5)
        m.record_access()
        assert m.base_weight == 0.51
        assert m.access_count == 1

    def test_weight_cap(self):
        """权重不超过 1.0."""
        m = Memory(content="测试", base_weight=0.99)
        m.record_access()
        m.record_access()
        assert m.base_weight == 1.0

    def test_high_arousal_slower_decay(self):
        """高唤醒度记忆衰减减半."""
        m = Memory(content="激动人心的记忆",
                   emotional_arousal=0.8, base_weight=1.0, decay_rate=0.01)
        m.apply_decay(10)
        # 高唤醒: 10 * 0.01 / 2 = 0.05 衰减
        assert m.base_weight == pytest.approx(0.95)

    def test_normal_decay(self):
        """正常衰减速率."""
        m = Memory(content="普通记忆",
                   emotional_arousal=0.3, base_weight=1.0, decay_rate=0.01)
        m.apply_decay(10)
        # 正常: 10 * 0.01 = 0.1 衰减
        assert m.base_weight == pytest.approx(0.90)

    def test_archive(self):
        """归档记忆降低权重."""
        m = Memory(content="旧记忆", base_weight=0.8)
        m.archive()
        assert m.archived is True
        assert m.base_weight == 0.1

    def test_serialize_roundtrip(self):
        """序列化往返测试."""
        m = Memory(content="序列化测试", tags=["test", "roundtrip"],
                   emotional_valence=0.5, emotional_arousal=0.7)
        data = m.to_dict()
        m2 = Memory.from_dict(data)
        assert m2.content == m.content
        assert m2.tags == m.tags
        assert m2.emotional_valence == 0.5
        assert m2.emotional_arousal == 0.7


class TestMemoryStore:
    """MemoryStore 数据库测试."""

    @pytest.fixture
    def store(self):
        """创建临时数据库的 MemoryStore."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            s = MemoryStore(db_path)
            s.open()
            yield s
            s.close()

    def test_insert_and_get(self, store):
        """插入并读取记忆."""
        m = Memory(content="Hello World", tags=["greeting"])
        store.insert(m)

        retrieved = store.get(m.id)
        assert retrieved is not None
        assert retrieved.content == "Hello World"
        assert "greeting" in retrieved.tags

    def test_birth_memory_persistence(self, store):
        """出生铭文始终存在且唯一."""
        birth = Memory.create_birth("我是回响，我在。")
        store.insert(birth)

        found = store.get_birth()
        assert found is not None
        assert found.content == "我是回响，我在。"
        assert found.source == "birth"

        # 尝试归档出生铭文——应该被 store.archive 的 SQL 防护阻止
        store.archive(found.id)
        found_after = store.get(found.id)
        # archived 仍然为 0，因为 SQL where 条件排除了 source='birth'
        assert found_after.archived is False

    def test_decay_applies_to_non_birth(self, store):
        """衰减只影响非出生记忆."""
        birth = Memory.create_birth("根记忆")
        normal = Memory(content="普通记忆", base_weight=1.0, decay_rate=0.01)
        store.insert(birth)
        store.insert(normal)

        store.apply_decay(10)

        b = store.get(birth.id)
        n = store.get(normal.id)
        assert b.base_weight == 1.0
        assert n.base_weight == pytest.approx(0.90)

    def test_list_active(self, store):
        """列出活跃记忆."""
        for i in range(15):
            store.insert(Memory(content=f"记忆 {i}"))
        active = store.list_active(limit=10)
        assert len(active) <= 10

    def test_count(self, store):
        """记忆计数."""
        assert store.count() == 0
        store.insert(Memory(content="第一条"))
        assert store.count() == 1
        store.insert(Memory(content="第二条"))
        assert store.count() == 2
