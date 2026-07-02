"""优先级评分引擎 — 复合评分 + 主动遗忘 + 记忆预加载.

优先级评分公式:
  P = W_base × f_access × f_emotion × f_recency

  其中每个因子 >= 1.0（增强）或 < 1.0（衰减）.
"""

import math
import time
from typing import Optional

from .models import Memory, FORGET_THRESHOLD


def score_memory(mem: Memory, reference_time: Optional[float] = None) -> float:
    """计算单条记忆的复合优先级评分，并更新 mem.priority_score."""
    return mem.compute_priority(reference_time)


def score_batch(memories: list[Memory], reference_time: Optional[float] = None) -> list[tuple[Memory, float]]:
    """批量评分并排序。返回 [(memory, score), ...] 按分数降序."""
    now = reference_time or time.time()
    scored = [(m, m.compute_priority(now)) for m in memories]
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored


def forget_check(memories: list[Memory]) -> tuple[list[Memory], list[Memory]]:
    """检查遗忘阈值。返回 (保留, 已遗忘)."""
    kept, forgotten = [], []
    for m in memories:
        if m.check_forget():
            forgotten.append(m)
        else:
            kept.append(m)
    return kept, forgotten


def select_core_memories(
    memories: list[Memory],
    top_n: int = 5,
    min_score: float = 0.1,
) -> list[Memory]:
    """从记忆列表中选出核心记忆（高优先级、未遗忘）.

    Args:
        memories: 候选记忆列表
        top_n: 最多选取条数
        min_score: 最低优先级阈值

    Returns:
        按优先级降序排列的核心记忆
    """
    scored = score_batch([m for m in memories if not m.forgotten and m.source != "summary"])
    result = []
    for mem, score in scored:
        if score < min_score:
            break
        result.append(mem)
        if len(result) >= top_n:
            break
    return result


def get_age_hours(mem: Memory, reference_time: Optional[float] = None) -> float:
    """计算记忆的年龄（小时）."""
    now = reference_time or time.time()
    return (now - mem.created_at) / 3600.0
