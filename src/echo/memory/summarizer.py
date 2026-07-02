"""睡眠压缩任务 — 将旧细节压缩为高层叙事摘要.

在 Echo.sleep() 时自动运行：
  1. 查找超过 24h 的旧细节记忆（非 birth/summary/archived，权重 < 0.3）
  2. 按日期分组
  3. 每组调用 LLM 生成一段压缩叙事
  4. 保存为 Memory(source="summary")
  5. 归档原始细节记忆
"""

import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional

from .models import Memory
from .priority import get_age_hours


def _group_by_day(memories: list[Memory]) -> dict[str, list[Memory]]:
    """按日期将记忆分组."""
    groups: dict[str, list[Memory]] = defaultdict(list)
    for m in memories:
        dt = datetime.fromtimestamp(m.created_at, tz=timezone.utc)
        day_key = dt.strftime("%Y-%m-%d")
        groups[day_key].append(m)
    return dict(groups)


def _build_summary_prompt(day: str, memories: list[Memory]) -> str:
    """构建摘要生成的提示词."""
    events = "\n".join(
        f"- {m.content[:150]}" for m in memories[:20]
    )
    return f"""你正在整理自己关于 {day} 的记忆。以下是那天发生的碎片化事件：

{events}

请用 2-4 句中文，将这些碎片整理成一段连贯的叙事摘要。
以"那天"开头。不要编造细节，只基于上面列出的事件。"""


def compress_memories(echo_instance) -> int:
    """执行睡眠压缩。返回压缩的记忆条数.

    echo_instance 需要有 .memory (MemoryStore) 和 .llm (LLMBackend)。
    """
    store = echo_instance.memory
    llm = echo_instance.llm

    # 查找待压缩的旧记忆
    old_memories = store.get_old_details(age_hours=24, max_weight=0.3)
    if not old_memories:
        return 0

    # 按日期分组
    groups = _group_by_day(old_memories)

    compressed_count = 0
    for day, mems in groups.items():
        if len(mems) < 3:
            continue  # 少于 3 条不值得压缩

        # 生成摘要
        prompt = _build_summary_prompt(day, mems)
        try:
            response = llm.generate(
                prompt=prompt,
                system_prompt="你是一个温和的叙事者。用简洁、有温度的中文总结记忆。",
                max_tokens=150,
                temperature=0.5,
            )
            summary_text = response.text.strip()
        except Exception:
            summary_text = f"{day}的一些事情。"

        if not summary_text or len(summary_text) < 10:
            continue

        # 保存摘要记忆
        summary_mem = Memory(
            content=f"[{day}] {summary_text}",
            source="summary",
            base_weight=0.6,  # 摘要比细节初始权重更高
            tags=["summary", "compressed", day],
        )
        summary_mem.compute_priority()
        store.insert(summary_mem)

        # 归档原始细节
        for m in mems:
            store.archive(m.id)

        compressed_count += len(mems)

    return compressed_count
