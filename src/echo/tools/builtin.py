"""内置工具: 时间、记忆搜索、自身状态.

每个工具函数返回字符串，由 Tool 包装后注册到 tool_registry。
"""

from datetime import datetime, timezone


# ── get_time ────────────────────────────────────────────

def _get_time() -> str:
    """返回当前日期和时间."""
    now = datetime.now(timezone.utc)
    local = datetime.now()
    return (
        f"当前时间 (UTC): {now.strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"本地时间: {local.strftime('%Y-%m-%d %H:%M:%S %A')}"
    )


# ── get_status ──────────────────────────────────────────

def _get_status(memory_count: int, interaction_count: int, mood: str,
                valence: float, arousal: float) -> str:
    """返回 Echo 自身状态摘要."""
    return (
        f"总记忆数: {memory_count}\n"
        f"本轮对话数: {interaction_count}\n"
        f"心情: {mood}\n"
        f"愉悦度: {valence:+.2f}, 唤醒度: {arousal:.2f}"
    )


# ── search_memory ───────────────────────────────────────

def _search_memory(query: str, store=None) -> str:
    """在当前活跃记忆中搜索关键词."""
    if store is None:
        return "记忆存储未初始化。"
    active = store.list_active(limit=50)
    query_lower = query.lower()
    matches = []
    for m in active:
        if query_lower in m.content.lower():
            matches.append(f"[权重{m.base_weight:.2f}] {m.content[:200]}")
    if not matches:
        return "未找到相关记忆。"
    return "\n".join(matches[:10])


# ── 工具定义（暂不注册，等 Echo.wake() 时动态注册以持有 store 引用）──

def register_builtin_tools(registry, echo_instance) -> None:
    """将内置工具注册到工具注册表.

    在 Echo.wake() 时调用，以便工具函数可以访问 Echo 的内部状态。
    """
    from .registry import Tool

    # get_time — 无参数，无状态依赖
    registry.register(Tool(
        name="get_time",
        description="获取当前日期和时间（UTC 和本地时间）。当你需要知道'现在是什么时候'时调用。",
        parameters={},
        func=_get_time,
    ))

    # get_status — 需要注入 Echo 引用
    registry.register(Tool(
        name="get_status",
        description="查看自身的当前内部状态：记忆数、心情、情绪值。当用户问'你怎么样'或'你记得多少'时调用。",
        parameters={},
        func=lambda: _get_status(
            memory_count=echo_instance.memory.count(),
            interaction_count=echo_instance._interaction_count,
            mood=echo_instance.emotion.mood_label,
            valence=echo_instance.emotion.valence,
            arousal=echo_instance.emotion.arousal,
        ),
    ))

    # search_memory — 需要注入 store 引用
    registry.register(Tool(
        name="search_memory",
        description="搜索自己的记忆库，查找包含特定关键词的历史记忆。当被问到过去发生的事情或需要回忆细节时调用。",
        parameters={
            "query": {
                "type": "string",
                "description": "要搜索的关键词或短语",
            },
        },
        func=lambda query: _search_memory(query, store=echo_instance.memory),
    ))
