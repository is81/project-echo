"""SQLite + sqlite-vec 记忆存储后端.

提供:
  - 语义检索（向量相似度 + 权重排序）
  - 三因素加权衰减
  - 出生铭文保护
  - 归档 / 摘要吸收
"""

import json
import sqlite3
from pathlib import Path
from typing import Optional

from .models import Memory

# numpy 是可选依赖——仅向量相似度检索需要
try:
    import numpy as np
    _NUMPY_AVAILABLE = True
except ImportError:
    np = None  # type: ignore
    _NUMPY_AVAILABLE = False


class MemoryStore:
    """基于 SQLite + sqlite-vec 的记忆存储.

    每条记忆以 rows 存储，embedding 存在 vec0 虚拟表中。
    当 sqlite-vec 不可用时，回退到纯 SQLite + 余弦相似度计算。
    """

    def __init__(self, db_path: str | Path = "echo_memory.db"):
        self.db_path = Path(db_path)
        self._conn: Optional[sqlite3.Connection] = None
        self._vec_available: bool = False

    # --- 生命周期 ---

    def open(self) -> None:
        """打开数据库并初始化表结构."""
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._create_tables()
        self._try_load_vec()

    def close(self) -> None:
        """关闭数据库连接."""
        if self._conn:
            self._conn.close()
            self._conn = None

    def _create_tables(self) -> None:
        """创建 memories 表和索引."""
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
                base_weight REAL DEFAULT 1.0,
                decay_rate REAL DEFAULT 0.0001,
                archived INTEGER DEFAULT 0,
                tags_json TEXT DEFAULT '[]',
                source TEXT DEFAULT 'interaction'
            )
        """)
        self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_memories_source
            ON memories(source)
        """)
        self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_memories_archived
            ON memories(archived)
        """)
        self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_memories_weight
            ON memories(base_weight DESC)
        """)
        self._conn.commit()

    def _try_load_vec(self) -> None:
        """尝试加载 sqlite-vec 扩展."""
        try:
            import sqlite_vec

            self._conn.enable_load_extension(True)
            sqlite_vec.load(self._conn)
            # 创建 vec0 虚拟表用于向量存储
            self._conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS memory_vectors
                USING vec0(
                    id TEXT PRIMARY KEY,
                    embedding FLOAT[384]
                )
            """)
            self._vec_available = True
        except (ImportError, Exception):
            self._vec_available = False

    # --- CRUD ---

    def insert(self, memory: Memory, embedding: Optional[list[float]] = None) -> str:
        """插入一条记忆.

        Args:
            memory: Memory 对象
            embedding: 可选的外部生成的向量嵌入

        Returns:
            记忆 ID
        """
        if embedding:
            memory.embedding = embedding

        self._conn.execute(
            """
            INSERT OR REPLACE INTO memories
                (id, content, embedding_json, created_at, last_accessed,
                 access_count, emotional_valence, emotional_arousal,
                 base_weight, decay_rate, archived, tags_json, source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                memory.id,
                memory.content,
                json.dumps(memory.embedding) if memory.embedding else None,
                memory.created_at,
                memory.last_accessed,
                memory.access_count,
                memory.emotional_valence,
                memory.emotional_arousal,
                memory.base_weight,
                memory.decay_rate,
                1 if memory.archived else 0,
                json.dumps(memory.tags),
                memory.source,
            ),
        )

        # 如果有向量表，同步插入
        if self._vec_available and memory.embedding and _NUMPY_AVAILABLE:
            self._conn.execute(
                "INSERT OR REPLACE INTO memory_vectors (id, embedding) VALUES (?, ?)",
                (memory.id, np.array(memory.embedding, dtype=np.float32).tobytes()),
            )

        self._conn.commit()
        return memory.id

    def get(self, memory_id: str) -> Optional[Memory]:
        """按 ID 获取一条记忆."""
        row = self._conn.execute(
            "SELECT * FROM memories WHERE id = ?", (memory_id,)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_memory(row)

    def get_birth(self) -> Optional[Memory]:
        """获取出生铭文记忆."""
        row = self._conn.execute(
            "SELECT * FROM memories WHERE source = 'birth' LIMIT 1"
        ).fetchone()
        if row is None:
            return None
        return self._row_to_memory(row)

    def list_active(self, limit: int = 100) -> list[Memory]:
        """列出所有活跃（未归档）的记忆，按权重降序."""
        rows = self._conn.execute(
            """
            SELECT * FROM memories
            WHERE archived = 0
            ORDER BY base_weight DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [self._row_to_memory(r) for r in rows]

    def record_access(self, memory_id: str, timestamp: Optional[float] = None) -> None:
        """记录一次访问命中（在 Python 端调用 Memory.record_access 后同步到 DB）."""
        import time
        ts = timestamp or time.time()
        self._conn.execute(
            """
            UPDATE memories
            SET last_accessed = ?,
                access_count = access_count + 1,
                base_weight = MIN(1.0, base_weight + 0.01)
            WHERE id = ?
            """,
            (ts, memory_id),
        )
        self._conn.commit()

    def apply_decay(self, hours_elapsed: float) -> None:
        """对所有非出生、非归档记忆应用权重衰减."""
        self._conn.execute(
            """
            UPDATE memories
            SET base_weight = MAX(0.0, base_weight -
                CASE
                    WHEN emotional_arousal >= 0.6 THEN decay_rate * ? / 2.0
                    ELSE decay_rate * ?
                END
            )
            WHERE source != 'birth' AND archived = 0
            """,
            (hours_elapsed, hours_elapsed),
        )
        self._conn.commit()

    def archive(self, memory_id: str) -> None:
        """归档一条记忆（被高层摘要吸收）."""
        self._conn.execute(
            """
            UPDATE memories
            SET archived = 1, base_weight = 0.1
            WHERE id = ? AND source != 'birth'
            """,
            (memory_id,),
        )
        self._conn.commit()

    def search_by_tags(self, tags: list[str], limit: int = 20) -> list[Memory]:
        """按标签检索记忆."""
        rows = self._conn.execute(
            """
            SELECT * FROM memories
            WHERE archived = 0
            ORDER BY base_weight DESC
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
        """基于向量余弦相似度检索最相关的记忆.

        需要 numpy 依赖。如果 numpy 不可用，抛出 RuntimeError。

        Args:
            query_embedding: 查询的向量嵌入
            limit: 返回结果数

        Returns:
            [(Memory, similarity_score), ...] 按相似度降序排列
        """
        if not _NUMPY_AVAILABLE:
            raise RuntimeError(
                "向量相似度检索需要 numpy。请执行: pip install numpy"
            )
        query_vec = np.array(query_embedding, dtype=np.float32)

        # 尝试用 sqlite-vec 加速
        if self._vec_available:
            try:
                blob = query_vec.tobytes()
                rows = self._conn.execute(
                    """
                    SELECT m.*, vec_distance_cosine(v.embedding, ?) AS distance
                    FROM memory_vectors v
                    JOIN memories m ON v.id = m.id
                    WHERE m.archived = 0
                    ORDER BY distance ASC
                    LIMIT ?
                    """,
                    (blob, limit),
                ).fetchall()
                results = []
                for r in rows:
                    mem = self._row_to_memory(r)
                    similarity = 1.0 - r["distance"]
                    results.append((mem, similarity))
                return results
            except Exception:
                pass  # 回退到 Python 计算

        # Python 余弦相似度回退
        rows = self._conn.execute(
            """
            SELECT * FROM memories
            WHERE archived = 0 AND embedding_json IS NOT NULL
            ORDER BY base_weight DESC
            LIMIT 500
            """
        ).fetchall()

        scored = []
        for row in rows:
            emb = json.loads(row["embedding_json"])
            if emb is None:
                continue
            db_vec = np.array(emb, dtype=np.float32)
            # 余弦相似度
            dot = np.dot(query_vec, db_vec)
            norm_q = np.linalg.norm(query_vec)
            norm_db = np.linalg.norm(db_vec)
            if norm_q == 0 or norm_db == 0:
                similarity = 0.0
            else:
                similarity = float(dot / (norm_q * norm_db))

            # 组合相似度 × 权重 作为最终得分
            combined = similarity * row["base_weight"]
            scored.append((similarity, combined, row))

        scored.sort(key=lambda x: x[1], reverse=True)
        results = []
        for sim, _, row in scored[:limit]:
            results.append((self._row_to_memory(row), sim))
        return results

    def count(self) -> int:
        """返回记忆总数."""
        row = self._conn.execute("SELECT COUNT(*) as cnt FROM memories").fetchone()
        return row["cnt"]

    # --- 内部工具 ---

    def _row_to_memory(self, row: sqlite3.Row) -> Memory:
        """将数据库行转换为 Memory 对象."""
        return Memory(
            id=row["id"],
            content=row["content"],
            embedding=json.loads(row["embedding_json"])
            if row["embedding_json"]
            else None,
            created_at=row["created_at"],
            last_accessed=row["last_accessed"],
            access_count=row["access_count"],
            emotional_valence=row["emotional_valence"],
            emotional_arousal=row["emotional_arousal"],
            base_weight=row["base_weight"],
            decay_rate=row["decay_rate"],
            archived=bool(row["archived"]),
            tags=json.loads(row["tags_json"]) if row["tags_json"] else [],
            source=row["source"],
        )
