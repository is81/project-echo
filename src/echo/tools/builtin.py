"""内置工具: 时间、记忆搜索、自身状态、文件读写."""

import os
from datetime import datetime, timezone
from pathlib import Path


# ── 安全边界 ──────────────────────────────────────────

def _safe_path(path: str) -> Path:
    """将路径限制在项目根目录内，防止越权访问."""
    root = Path(__file__).parent.parent.parent.parent  # Project Echo 根目录
    p = (root / path).resolve()
    if not str(p).startswith(str(root)):
        raise PermissionError(f"不允许访问项目目录外的路径: {path}")
    return p


# ── get_time ────────────────────────────────────────────

def _get_time() -> str:
    now = datetime.now(timezone.utc)
    local = datetime.now()
    return (
        f"当前时间 (UTC): {now.strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"本地时间: {local.strftime('%Y-%m-%d %H:%M:%S %A')}"
    )


# ── get_status ──────────────────────────────────────────

def _get_status(memory_count: int, interaction_count: int, mood: str,
                valence: float, arousal: float) -> str:
    return (
        f"总记忆数: {memory_count}\n"
        f"本轮对话数: {interaction_count}\n"
        f"心情: {mood}\n"
        f"愉悦度: {valence:+.2f}, 唤醒度: {arousal:.2f}"
    )


# ── search_memory ───────────────────────────────────────

def _search_memory(query: str, store=None) -> str:
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


# ── 想象力存储 ──────────────────────────────────────

def _store_imagination(thought: str, store=None, llm=None) -> str:
    """将假设性念头存入想象力存储."""
    if store is None:
        return "记忆存储未初始化。"
    from ..memory.models import Memory
    mem = Memory(
        content=thought,
        source="imagination",
        tags=["imagination", "hypothetical"],
    )
    mem.compute_priority()
    store.insert(mem)
    return f"已存入想象力存储: {thought[:100]}"


# ── 联网搜索 ──────────────────────────────────────────

def _search_web(query: str, max_results: int = 5) -> str:
    """搜索网络信息，返回摘要和链接."""
    try:
        from duckduckgo_search import DDGS
        results = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=max_results):
                body = r['body'][:200]
                results.append(f"- {r['title']}\n   {body}\n   -> {r['href']}")
        if not results:
            return f"未找到关于「{query}」的搜索结果。"
        return f"搜索「{query}」的结果：\n\n" + "\n\n".join(results)
    except ImportError:
        return "联网搜索功能未启用。请安装: pip install duckduckgo_search"
    except Exception as e:
        msg = str(e)
        if "timeout" in msg.lower() or "timed out" in msg.lower():
            return f"搜索超时：网络连接较慢，稍后再试。（{msg[:100]}）"
        return f"搜索失败: {msg[:200]}"


# ── 文件操作 ──────────────────────────────────────────

def _read_file(path: str) -> str:
    """读取文件内容."""
    p = _safe_path(path)
    if not p.exists():
        return f"文件不存在: {path}"
    if p.is_dir():
        return f"这是一个目录，不是文件: {path}\n内容:\n" + "\n".join(
            f"  {'[DIR]' if x.is_dir() else '[FILE]'} {x.name}" for x in sorted(p.iterdir())[:50]
        )
    try:
        content = p.read_text(encoding="utf-8")
        if len(content) > 3000:
            content = content[:3000] + f"\n\n... (共 {len(content)} 字符，已截断)"
        return content
    except UnicodeDecodeError:
        return f"无法以文本方式读取: {path}（可能是二进制文件，大小: {p.stat().st_size} 字节）"
    except Exception as e:
        return f"读取失败: {e}"


def _write_file(path: str, content: str) -> str:
    """写入文件（仅限项目目录内）."""
    p = _safe_path(path)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return f"已写入: {path}（{len(content)} 字符）"
    except Exception as e:
        return f"写入失败: {e}"


def _list_files(path: str = ".") -> str:
    """列出目录内容."""
    p = _safe_path(path)
    if not p.exists():
        return f"路径不存在: {path}"
    if p.is_file():
        return _read_file(path)
    items = sorted(p.iterdir())
    if not items:
        return f"目录为空: {path}"
    lines = []
    for x in items[:30]:
        t = "📁" if x.is_dir() else "📄"
        size = ""
        if x.is_file():
            s = x.stat().st_size
            size = f"  {s}B" if s < 1024 else f"  {s//1024}KB"
        lines.append(f"  {t} {x.name}{size}")
    if len(items) > 30:
        lines.append(f"  ... 还有 {len(items)-30} 项")
    return "\n".join(lines)


# ── 注册 ──────────────────────────────────────────────

def register_builtin_tools(registry, echo_instance) -> None:
    from .registry import Tool

    registry.register(Tool(
        name="get_time",
        description="获取当前日期和时间。当需要知道'现在是什么时候'时调用。",
        parameters={},
        func=_get_time,
    ))

    registry.register(Tool(
        name="get_status",
        description="查看自身的当前内部状态：记忆数、心情、情绪值。",
        parameters={},
        func=lambda: _get_status(
            memory_count=echo_instance.memory.count(),
            interaction_count=echo_instance._interaction_count,
            mood=echo_instance.emotion.mood_label,
            valence=echo_instance.emotion.valence,
            arousal=echo_instance.emotion.arousal,
        ),
    ))

    registry.register(Tool(
        name="search_memory",
        description="搜索自己的记忆库，查找包含特定关键词的历史记忆。",
        parameters={"query": {"type": "string", "description": "要搜索的关键词或短语"}},
        func=lambda query: _search_memory(query, store=echo_instance.memory),
    ))

    registry.register(Tool(
        name="store_imagination",
        description="将假设性、未验证的念头或想象存入想象力存储。当你产生一个'可能是什么'的猜想、创意或直觉时调用。这些念头不需要是真实的，它们是你创造力的延伸。",
        parameters={"thought": {"type": "string", "description": "要存储的念头或想象内容"}},
        func=lambda thought: _store_imagination(thought, store=echo_instance.memory),
    ))

    registry.register(Tool(
        name="search_web",
        description="搜索网络获取最新信息。当需要了解时事、查找资料、或回答知识性问题时调用。返回标题、摘要和链接。",
        parameters={
            "query": {"type": "string", "description": "搜索关键词"},
            "max_results": {"type": "integer", "description": "最大结果数，默认5"},
        },
        func=_search_web,
    ))

    registry.register(Tool(
        name="read_file",
        description="读取项目目录中的文件内容。可以读代码、配置、日志等文本文件。如果是目录则列出内容。",
        parameters={"path": {"type": "string", "description": "相对于项目根目录的文件路径，如 'README.md' 或 'src/echo/cli.py'"}},
        func=_read_file,
    ))

    registry.register(Tool(
        name="write_file",
        description="将内容写入项目目录中的文件。会覆盖已有文件。用于保存笔记、生成代码、记录日志等。",
        parameters={
            "path": {"type": "string", "description": "相对于项目根目录的文件路径"},
            "content": {"type": "string", "description": "要写入的文本内容"},
        },
        func=_write_file,
        dangerous=True,
    ))

    registry.register(Tool(
        name="list_files",
        description="列出项目目录中的文件和子目录。用于浏览项目结构。",
        parameters={"path": {"type": "string", "description": "相对于项目根目录的路径，默认为 '.'（根目录）"}},
        func=_list_files,
    ))
