"""SQLite + sqlite-vec 记忆存储后端.

提供:
  - 语义检索（向量相似度 + 优先级排序）
  - 指数半衰期衰减
  - 主动遗忘（低优先级自动标记）
  - 出生铭文保护
  - 归档 / 摘要吸收
"""

import json
import math
import sqlite3
import time
from pathlib import Path
from typing import Optional

from .models import (
    Memory, DEFAULT_HALF_LIFE_HOURS,
    HIGH_AROUSAL_HALF_LIFE_HOURS, HIGH_AROUSAL_THRESHOLD,
    FORGET_THRESHOLD, ACCESS_BOOST,
)

# numpy 可选
try:
    import numpy as np
    _NUMPY_AVAILABLE = True
except ImportError:
    np = None  # type: ignore
    _NUMPY_AVAILABLE = False


class MemoryStore:
    """基于 SQLite + sqlite-vec 的记忆存储."""

    def __init__(self, db_path: str | Path = "echo_memory.db"):
        self.db_path = Path(db_path)
        self._conn: Optional[sqlite3.Connection] = None
        self._vec_available: bool = False

    # --- 生命周期 ---

    def open(self) -> None:
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._create_tables()
        self._migrate_schema()     # 必须在 _create_tables() 后，为旧库添加新列
        self._create_indexes()     # 索引创建在迁移后，确保列已存在
        self._try_load_vec()

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    def _create_tables(self) -> None:
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                id TEXT PRIMARY KEY,
                content TEXT NOT NULL,
                embedding_json TEXT,
                created_at REAL NOT NULL,
                last_accessed REAL NOT NULL,
                access_count INTEGER DEFAULT 0,
                emotional_valence REAL DEFAULT 0.0,
                emotional_arousal REAL DEFAULT 0.0,
                base_weight REAL DEFAULT 0.5,
                priority_score REAL DEFAULT 0.5,
                half_life_hours REAL DEFAULT 168.0,
                archived INTEGER DEFAULT 0,
                forgotten INTEGER DEFAULT 0,
                tags_json TEXT DEFAULT '[]',
                source TEXT DEFAULT 'interaction'
            )
        """)
        # 基础索引（只涉及建表时就存在的列）
        for idx in [
            "CREATE INDEX IF NOT EXISTS idx_memories_source ON memories(source)",
            "CREATE INDEX IF NOT EXISTS idx_memories_archived ON memories(archived)",
        ]:
            self._conn.execute(idx)
        self._conn.commit()

    def _create_indexes(self) -> None:
        """在迁移后创建索引，确保所有列都已存在."""
        for idx in [
            "CREATE INDEX IF NOT EXISTS idx_memories_forgotten ON memories(forgotten)",
            "CREATE INDEX IF NOT EXISTS idx_memories_priority ON memories(priority_score DESC)",
        ]:
            try:
                self._conn.execute(idx)
            except sqlite3.OperationalError:
                pass  # 列可能还不存在（极端情况）
        self._conn.commit()

    def _migrate_schema(self) -> None:
        """兼容旧数据库：添加新列（如果不存在）."""
        existing = {r[1] for r in self._conn.execute("PRAGMA table_info(memories)").fetchall()}
        migrations = {
            "priority_score": "ALTER TABLE memories ADD COLUMN priority_score REAL DEFAULT 0.5",
            "half_life_hours": "ALTER TABLE memories ADD COLUMN half_life_hours REAL DEFAULT 168.0",
            "forgotten": "ALTER TABLE memories ADD COLUMN forgotten INTEGER DEFAULT 0",
        }
        for col, sql in migrations.items():
            if col not in existing:
                try:
                    self._conn.execute(sql)
                except sqlite3.OperationalError:
                    pass
        self._conn.commit()

    def _try_load_vec(self) -> None:
        try:
            import sqlite_vec
            self._conn.enable_load_extension(True)
            sqlite_vec.load(self._conn)
            self._conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS memory_vectors
                USING vec0(id TEXT PRIMARY KEY, embedding FLOAT[384])
            """)
            self._vec_available = True
        except (ImportError, Exception):
            self._vec_available = False

    # --- CRUD ---

    def insert(self, memory: Memory, embedding: Optional[list[float]] = None) -> str:
        if embedding:
            memory.embedding = embedding
        # 确保 priority_score 是最新的
        memory.compute_priority()

        self._conn.execute(
            """
            INSERT OR REPLACE INTO memories
                (id, content, embedding_json, created_at, last_accessed,
                 access_count, emotional_valence, emotional_arousal,
                 base_weight, priority_score, half_life_hours,
                 archived, forgotten, tags_json, source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                memory.id, memory.content,
                json.dumps(memory.embedding) if memory.embedding else None,
                memory.created_at, memory.last_accessed,
                memory.access_count, memory.emotional_valence, memory.emotional_arousal,
                memory.base_weight, memory.priority_score, memory.half_life_hours,
                1 if memory.archived else 0, 1 if memory.forgotten else 0,
                json.dumps(memory.tags), memory.source,
            ),
        )

        if self._vec_available and memory.embedding and _NUMPY_AVAILABLE:
            self._conn.execute(
                "INSERT OR REPLACE INTO memory_vectors (id, embedding) VALUES (?, ?)",
                (memory.id, np.array(memory.embedding, dtype=np.float32).tobytes()),
            )

        self._conn.commit()
        return memory.id

    def get(self, memory_id: str) -> Optional[Memory]:
        row = self._conn.execute("SELECT * FROM memories WHERE id = ?", (memory_id,)).fetchone()
        return self._row_to_memory(row) if row else None

    def get_birth(self) -> Optional[Memory]:
        row = self._conn.execute(
            "SELECT * FROM memories WHERE source = 'birth' LIMIT 1"
        ).fetchone()
        return self._row_to_memory(row) if row else None

    def list_active(self, limit: int = 100) -> list[Memory]:
        """列出活跃（未归档、未遗忘）记忆，按优先级降序."""
        rows = self._conn.execute(
            """
            SELECT * FROM memories
            WHERE archived = 0 AND forgotten = 0
            ORDER BY priority_score DESC
            LIMIT ?
            """, (limit,),
        ).fetchall()
        return [self._row_to_memory(r) for r in rows]

    def get_core_memories(self, n: int = 5) -> list[Memory]:
        """获取核心记忆（高优先级，非出生/摘要），用于预加载."""
        rows = self._conn.execute(
            """
            SELECT * FROM memories
            WHERE archived = 0 AND forgotten = 0
              AND source NOT IN ('birth', 'summary')
            ORDER BY priority_score DESC
            LIMIT ?
            """, (n,),
        ).fetchall()
        return [self._row_to_memory(r) for r in rows]

    def get_old_details(self, age_hours: float = 24, max_weight: float = 0.3) -> list[Memory]:
        """查找旧细节记忆（用于睡眠压缩）.

        条件: 超过 age_hours 小时、权重低于 max_weight、非 birth/summary、未归档。
        """
        cutoff = time.time() - age_hours * 3600
        rows = self._conn.execute(
            """
            SELECT * FROM memories
            WHERE archived = 0 AND forgotten = 0
              AND source NOT IN ('birth', 'summary')
              AND created_at < ?
              AND priority_score < ?
            ORDER BY created_at ASC
            LIMIT 100
            """, (cutoff, max_weight),
        ).fetchall()
        return [self._row_to_memory(r) for r in rows]

    def record_access(self, memory_id: str, timestamp: Optional[float] = None) -> None:
        """记录一次检索命中：+access_count, +weight boost, 刷新时间."""
        ts = timestamp or time.time()
        self._conn.execute(
            """
            UPDATE memories
            SET last_accessed = ?,
                access_count = access_count + 1,
                base_weight = MIN(1.0, base_weight + ?),
                half_life_hours = CASE
                    WHEN access_count > 3
                    THEN MIN(672.0, half_life_hours * 1.02)
                    ELSE half_life_hours
                END
            WHERE id = ?
            """, (ts, ACCESS_BOOST, memory_id),
        )
        self._conn.commit()
        # 更新后重算优先级
        self._recalc_priority(memory_id)

    # ── 半衰期衰减 ──────────────────────────────────

    def apply_half_life(self, hours_elapsed: float) -> int:
        """对所有非 birth、非归档记忆应用指数半衰期衰减.

        base_weight *= 0.5 ^ (hours_elapsed / half_life_hours)

        Returns:
            受影响的记忆数
        """
        # 使用 SQL 批量更新：指数衰减公式
        self._conn.execute(
            """
            UPDATE memories
            SET base_weight = MAX(0.0, base_weight * POW(0.5, ? / half_life_hours)),
                half_life_hours = CASE
                    WHEN emotional_arousal >= ? THEN ?
                    ELSE ?
                END
            WHERE source != 'birth' AND archived = 0 AND half_life_hours > 0
            """, (
                hours_elapsed,
                HIGH_AROUSAL_THRESHOLD, HIGH_AROUSAL_HALF_LIFE_HOURS,
                DEFAULT_HALF_LIFE_HOURS,
            ),
        )
        affected = self._conn.total_changes
        self._conn.commit()

        # 批量重算优先级
        self._recalc_all_priorities()
        return affected

    # ── 主动遗忘 ────────────────────────────────────

    def forget_low_priority(self, threshold: float = FORGET_THRESHOLD) -> int:
        """将优先级低于阈值的记忆标记为遗忘.

        Birth 和 archived 记忆不受影响。

        Returns:
            被遗忘的记忆数
        """
        self._conn.execute(
            """
            UPDATE memories
            SET forgotten = 1
            WHERE source != 'birth' AND archived = 0
              AND priority_score < ?
            """, (threshold,),
        )
        count = self._conn.total_changes
        self._conn.commit()
        return count

    # ── 归档 ────────────────────────────────────────

    def archive(self, memory_id: str) -> None:
        """归档一条记忆."""
        self._conn.execute(
            """
            UPDATE memories
            SET archived = 1, base_weight = 0.1, forgotten = 0
            WHERE id = ? AND source != 'birth'
            """, (memory_id,),
        )
        self._conn.commit()

    # ── 计数 ────────────────────────────────────────

    def count(self, include_forgotten: bool = False) -> int:
        if include_forgotten:
            row = self._conn.execute("SELECT COUNT(*) as cnt FROM memories").fetchone()
        else:
            row = self._conn.execute(
                "SELECT COUNT(*) as cnt FROM memories WHERE forgotten = 0"
            ).fetchone()
        return row["cnt"]

    # ── 搜索 ────────────────────────────────────────

    def search_by_tags(self, tags: list[str], limit: int = 20) -> list[Memory]:
        rows = self._conn.execute(
            """
            SELECT * FROM memories
            WHERE archived = 0 AND forgotten = 0
            ORDER BY priority_score DESC
            LIMIT 500
            """
        ).fetchall()
        results = []
        for row in rows:
            mem_tags = json.loads(row["tags_json"])
            if any(t in mem_tags for t in tags):
                results.append(self._row_to_memory(row))
                if len(results) >= limit:
                    break
        return results

    def search_by_similarity(
        self, query_embedding: list[float], limit: int = 10
    ) -> list[tuple[Memory, float]]:
        if not _NUMPY_AVAILABLE:
            raise RuntimeError("向量相似度检索需要 numpy。pip install numpy")

        query_vec = np.array(query_embedding, dtype=np.float32)

        if self._vec_available:
            try:
                blob = query_vec.tobytes()
                rows = self._conn.execute(
                    """
                    SELECT m.*, vec_distance_cosine(v.embedding, ?) AS distance
                    FROM memory_vectors v
                    JOIN memories m ON v.id = m.id
                    WHERE m.archived = 0 AND m.forgotten = 0
                    ORDER BY distance ASC
                    LIMIT ?
                    """, (blob, limit),
                ).fetchall()
                return [(self._row_to_memory(r), 1.0 - r["distance"]) for r in rows]
            except Exception:
                pass

        rows = self._conn.execute(
            """
            SELECT * FROM memories
            WHERE archived = 0 AND forgotten = 0 AND embedding_json IS NOT NULL
            ORDER BY priority_score DESC
            LIMIT 500
            """
        ).fetchall()

        scored = []
        for row in rows:
            emb = json.loads(row["embedding_json"])
            if not emb:
                continue
            db_vec = np.array(emb, dtype=np.float32)
            dot = np.dot(query_vec, db_vec)
            nq, nd = np.linalg.norm(query_vec), np.linalg.norm(db_vec)
            sim = float(dot / (nq * nd)) if nq and nd else 0.0
            combined = sim * row["priority_score"]
            scored.append((sim, combined, row))
        scored.sort(key=lambda x: x[1], reverse=True)
        return [(self._row_to_memory(r), s) for s, _, r in scored[:limit]]

    # ── 内部 ────────────────────────────────────────

    def _recalc_priority(self, memory_id: str) -> None:
        """重算单条记忆的优先级评分."""
        row = self._conn.execute(
            "SELECT * FROM memories WHERE id = ?", (memory_id,)
        ).fetchone()
        if not row:
            return
        mem = self._row_to_memory(row)
        mem.compute_priority()
        self._conn.execute(
            "UPDATE memories SET priority_score = ? WHERE id = ?",
            (mem.priority_score, memory_id),
        )
        self._conn.commit()

    def _recalc_all_priorities(self) -> None:
        """批量重算所有非 birth 记忆的优先级评分.

        P = base_weight * (1 + log(1+access)*0.1) * (1+|valence|*0.3+arousal*0.2) * 0.5^(age/halflife)
        """
        now = time.time()
        self._conn.execute(
            f"""
            UPDATE memories
            SET priority_score = base_weight
                * (1.0 + log(max(1, 1 + access_count)) * 0.1)
                * (1.0 + abs(emotional_valence) * 0.3 + emotional_arousal * 0.2)
                * CASE
                    WHEN half_life_hours <= 0 THEN 1.0
                    ELSE POW(0.5, ({now} - last_accessed) / 3600.0 / half_life_hours)
                  END
            WHERE source != 'birth'
            """
        )
        self._conn.commit()

    def _row_to_memory(self, row: sqlite3.Row) -> Memory:
        keys = row.keys()
        return Memory(
            id=row["id"],
            content=row["content"],
            embedding=json.loads(row["embedding_json"]) if row["embedding_json"] else None,
            created_at=row["created_at"],
            last_accessed=row["last_accessed"],
            access_count=row["access_count"],
            emotional_valence=row["emotional_valence"],
            emotional_arousal=row["emotional_arousal"],
            base_weight=row["base_weight"],
            priority_score=row["priority_score"] if "priority_score" in keys else 0.5,
            half_life_hours=row["half_life_hours"] if "half_life_hours" in keys else DEFAULT_HALF_LIFE_HOURS,
            archived=bool(row["archived"]),
            forgotten=bool(row["forgotten"]) if "forgotten" in keys else False,
            tags=json.loads(row["tags_json"]) if row["tags_json"] else [],
            source=row["source"],
        )
