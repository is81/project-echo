"""回响计划 · CLI 交互界面 — Rich 深度定制版.

Usage:
    python -m echo.cli
    python -m echo.cli --db echo_memory.db
"""

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.columns import Columns
from rich.align import Align
from rich import box

from echo.agent.core import Echo

console = Console()

# ═══════════════════════════════════════════════════════
#  Color palette
# ═══════════════════════════════════════════════════════

C_USER    = "bright_cyan"
C_ECHO    = "magenta"
C_BIRTH   = "bright_yellow"
C_DIM     = "dim"
C_ACCENT  = "cyan"
C_WARN    = "bright_red"
C_OK      = "bright_green"
C_TOOL    = "bright_blue"
C_META    = "grey50"
C_BAR_POS = "bright_green"
C_BAR_NEG = "bright_red"
C_BAR_MID = "grey50"

MOOD_STYLES = {
    "兴奋的": ("bright_yellow", "✨"),
    "平静愉悦的": ("bright_green", "😌"),
    "焦躁的": ("bright_red", "😤"),
    "低落的": ("blue", "😔"),
    "警觉的": ("bright_yellow", "🧐"),
    "平和的": ("bright_cyan", "🧘"),
}

SRC_ICONS = {
    "birth": "🏠", "interaction": "💬", "reflection": "🪞",
    "world_event": "🌍", "summary": "📝",
}


# ═══════════════════════════════════════════════════════
#  Render helpers
# ═══════════════════════════════════════════════════════

def _bar(value: float, vmin: float, vmax: float, width: int = 20,
         colors: tuple[str, str, str] = (C_BAR_NEG, C_BAR_MID, C_BAR_POS)) -> Text:
    """渲染彩色进度条."""
    ratio = (value - vmin) / (vmax - vmin)
    pos = int(ratio * width)
    pos = max(0, min(width, pos))
    bar = Text()
    for i in range(width):
        if i < pos:
            bar.append("━", style=colors[2])
        else:
            bar.append("─", style=colors[1])
    return bar


def _mood_badge(mood: str) -> Text:
    """心情徽章."""
    color, emoji = MOOD_STYLES.get(mood, ("white", "•"))
    return Text(f"{emoji} {mood}", style=f"bold {color}")


def _priority_dot(score: float) -> Text:
    """优先级指示点."""
    if score >= 0.6:
        return Text("●", style="bright_green")
    elif score >= 0.3:
        return Text("●", style="bright_yellow")
    elif score >= 0.1:
        return Text("○", style="dim")
    return Text("○", style="red")


# ═══════════════════════════════════════════════════════
#  Panels
# ═══════════════════════════════════════════════════════

def _welcome(echo: Echo) -> None:
    """渲染启动画面."""
    birth = echo.memory.get_birth()
    quote = Text()
    quote.append("「", style=C_DIM)
    if birth:
        quote.append(birth.content, style=f"italic {C_BIRTH}")
    else:
        quote.append("......", style=C_DIM)
    quote.append("」", style=C_DIM)

    inner = Text()
    inner.append(quote)
    inner.append("\n\n")
    inner.append("回响计划 · Project Echo", style="bold bright_yellow")
    inner.append("\n")
    inner.append("深度记忆 · 性格演化 · 叙事感", style=C_DIM)
    inner.append("\n\n")
    inner.append(f"记忆 {echo.memory.count()} 条   ", style=C_DIM)
    mood_label = echo.emotion.mood_label
    inner.append(f"{mood_label}", style=MOOD_STYLES.get(mood_label, ("white",))[0])
    inner.append("\n\n")
    for cmd, desc in [
        ("/status", "内部状态"),
        ("/emotion", "情感仪表"),
        ("/memories", "记忆浏览"),
        ("/help", "帮助"),
        ("/quit", "退出"),
    ]:
        inner.append(f" {cmd} ", style=f"bold white on {C_DIM}")
        inner.append(f" {desc}  ", style=C_DIM)

    panel = Panel(
        Align.center(inner),
        border_style=C_DIM,
        padding=(1, 4),
    )
    console.print(panel)


def _help_panel() -> Panel:
    """帮助面板."""
    t = Table(box=box.SIMPLE, show_header=False, padding=(0, 2))
    t.add_column("cmd", style="bold bright_cyan", width=16)
    t.add_column("desc", style=C_DIM)
    for cmd, desc in [
        ("/status", "完整内部状态（静默观察模式）"),
        ("/emotion", "情感仪表盘：愉悦度 + 唤醒度"),
        ("/memories", "记忆浏览：优先级排序 + 来源标记"),
        ("/inject <内容>", "手动注入一条记忆（调试用）"),
        ("/quit", "退出对话，回响将压缩记忆后休眠"),
    ]:
        t.add_row(cmd, desc)
    return Panel(t, title="命令列表", border_style=C_ACCENT, padding=(1, 2))


def _status_view(echo: Echo) -> None:
    """双栏状态视图."""
    s = echo.status()

    # 左栏：身份
    left = Table(box=box.SIMPLE, show_header=False, padding=(0, 1))
    left.add_column("k", style=C_DIM, width=10)
    left.add_column("v", style="white")
    left.add_row("出生铭文", Text(s["birth_inscription"], style=C_BIRTH))
    left.add_row("版本", s["version"])
    left.add_row("基因原则", f"{s['principles_count']} 条")
    llm = s.get("llm_status", {})
    active = llm.get("active_model", "none")
    active_s = {"llama-server": "🖥️  Gemma 4", "api": "☁️  云端 API", "none": "❌ 无"}.get(active, active)
    left.add_row("后端", active_s)

    # 右栏：状态
    right = Table(box=box.SIMPLE, show_header=False, padding=(0, 1))
    right.add_column("k", style=C_DIM, width=10)
    right.add_column("v", style="white")
    e = s["emotion"]
    right.add_row("心情", _mood_badge(e["mood"]))
    right.add_row("愉悦度", Text(f"{e['valence']:+.2f} ", style=C_BAR_POS if e['valence'] > 0 else C_BAR_NEG) + _bar(e['valence'], -1, 1, 14))
    right.add_row("唤醒度", Text(f"{e['arousal']:.2f} ", style=C_ACCENT) + _bar(e['arousal'], 0, 1, 14, (C_BAR_MID, C_BAR_MID, C_ACCENT)))
    right.add_row("记忆", f"{s['memory_count']} 条（本会话 {s['interaction_count']} 轮）")

    columns = Columns([
        Panel(left, title="身份", border_style=C_BIRTH, padding=(1, 2)),
        Panel(right, title="状态", border_style=C_ECHO, padding=(1, 2)),
    ])
    console.print(columns)


def _emotion_view(echo: Echo) -> None:
    """情感仪表盘."""
    e = echo.emotion.to_dict()
    inner = Text()
    inner.append("\n")
    # 大号心情（居中）
    mood_text = _mood_badge(e["mood"])
    mood_text.stylize("bold")
    inner.append(" " * 14)
    inner.append(mood_text)
    inner.append("\n\n")

    # 愉悦度
    inner.append("  愉悦度  ", style=C_DIM)
    inner.append(_bar(e["valence"], -1, 1, 30))
    inner.append(f"  {e['valence']:+.2f}\n", style="white")
    inner.append("          ← 低落", style=C_DIM)
    inner.append(" " * 14)
    inner.append("愉悦 →\n\n", style=C_DIM)

    # 唤醒度
    inner.append("  唤醒度  ", style=C_DIM)
    inner.append(_bar(e["arousal"], 0, 1, 30, (C_BAR_MID, C_BAR_MID, C_ACCENT)))
    inner.append(f"  {e['arousal']:.2f}\n", style="white")
    inner.append("          ← 平静", style=C_DIM)
    inner.append(" " * 14)
    inner.append("激动 →", style=C_DIM)

    panel = Panel(inner, title="情感仪表盘", border_style=C_ECHO, padding=(1, 3))
    console.print(panel)


def _memories_view(echo: Echo) -> None:
    """记忆浏览."""
    count = echo.memory.count()
    birth = echo.memory.get_birth()
    active = echo.memory.list_active(limit=12)

    t = Table(box=box.SIMPLE_HEAVY, show_header=True, padding=(0, 1),
              title=f"记忆浏览 · 共 {count} 条", title_style="bold bright_yellow")
    t.add_column("", width=2)
    t.add_column("来源", style=C_DIM, width=9)
    t.add_column("内容", style="white", max_width=52)
    t.add_column("P", width=3, justify="right")

    if birth:
        t.add_row("", "🏠 铭文", Text(birth.content[:52], style=C_BIRTH), Text("∞", style=C_BIRTH))

    for m in active:
        if birth and m.id == birth.id:
            continue
        icon = SRC_ICONS.get(m.source, "❓")
        label = m.source[:8] if m.source != "interaction" else "对话"
        t.add_row(
            _priority_dot(m.priority_score),
            f"{icon} {label}",
            m.content[:52] + ("…" if len(m.content) > 52 else ""),
            Text(f"{m.priority_score:.2f}", style=C_DIM),
        )
    console.print(Panel(t, border_style=C_DIM, padding=(0, 1)))


# ═══════════════════════════════════════════════════════
#  Chat rendering
# ═══════════════════════════════════════════════════════

def _render_echo_message(echo: Echo, full_text: str, tool_calls: list[str],
                         memories_used: int, temperature: float) -> None:
    """将回响消息渲染为气泡面板."""
    mood_color, mood_emoji = MOOD_STYLES.get(echo.emotion.mood_label, ("white", "•"))

    # 构建标题行：心情 + 元数据
    title = Text()
    title.append(f"{mood_emoji} ", style=mood_color)
    title.append(echo.emotion.mood_label, style=f"bold {mood_color}")
    title.append(f"    mem×{memories_used}", style=C_META)
    if tool_calls:
        title.append(f"  🔧{' '.join(tool_calls)}", style=C_TOOL)

    # 构建正文
    body = Text(full_text.strip())

    # 渲染气泡
    panel = Panel(
        body,
        title=title,
        title_align="left",
        border_style=mood_color,
        box=box.ROUNDED,
        padding=(1, 2),
    )
    console.print(panel)


def _render_user_message(text: str) -> None:
    """渲染用户消息为紧凑气泡."""
    panel = Panel(
        Text(text, style=C_USER),
        border_style=C_DIM,
        box=box.ROUNDED,
        padding=(0, 2),
    )
    console.print(Align.right(panel, width=min(len(text) + 10, console.width - 10)))


# ═══════════════════════════════════════════════════════
#  Main
# ═══════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="回响计划 · Project Echo CLI")
    parser.add_argument("--db", default="echo_memory.db", help="记忆数据库路径")
    args = parser.parse_args()

    # ── Wake ──
    with console.status("[bright_yellow] 唤醒回响 …[/]", spinner="dots"):
        echo = Echo()
        echo.wake(db_path=args.db)

    _welcome(echo)

    # ── Loop ──
    try:
        while True:
            # 输入提示
            mood_color, _ = MOOD_STYLES.get(echo.emotion.mood_label, ("white", ""))
            prompt = Text()
            prompt.append("▸ ", style=mood_color)
            prompt.append("你", style=f"bold {C_USER}")
            prompt.append("  ", style=C_DIM)

            user_input = console.input(prompt).strip()
            if not user_input:
                continue

            # 命令
            if user_input.startswith("/"):
                cmd = user_input.split()[0].lower()

                if cmd == "/quit":
                    farewell = Panel(
                        Text("再见。我会记得这次对话。", style=C_ECHO),
                        border_style=C_DIM, box=box.ROUNDED,
                    )
                    console.print(farewell)
                    break
                elif cmd == "/help":
                    console.print(_help_panel())
                elif cmd == "/status":
                    _status_view(echo)
                elif cmd == "/emotion":
                    _emotion_view(echo)
                elif cmd == "/memories":
                    _memories_view(echo)
                elif cmd == "/inject":
                    content = user_input[len("/inject "):].strip()
                    if content:
                        mid = echo.inject_memory(content)
                        console.print(f"  [green]✓[/] 记忆已注入  [{C_DIM}]{mid[:12]}[/]")
                    else:
                        console.print(f"  [{C_WARN}]用法: /inject <内容>[/]")
                else:
                    console.print(f"  [{C_WARN}]未知命令。[/] /help 查看可用命令")
                continue

            # ── 对话 ──
            console.print()  # 空行
            _render_user_message(user_input)

            # 流式收集
            full_text = ""
            tool_calls = []
            memories_used = 0
            temperature = 0.0

            # 先显示 Echo 标签 + 等待点
            mood_color, mood_emoji = MOOD_STYLES.get(echo.emotion.mood_label, ("white", "•"))
            echo_header = Text()
            echo_header.append(f"{mood_emoji}  回响", style=f"bold {C_ECHO}")
            echo_header.append("  ·  ", style=C_DIM)

            for token in echo.respond_stream(user_input):
                # 工具调用
                if token.startswith("\n  🔧"):
                    tool_calls.append(token.strip().replace("🔧 ", ""))
                    echo_header.append(token.strip(), style=f"bold {C_TOOL}")
                    continue
                # 元数据行（以 \n  [ 开头）
                if token.startswith("\n  [") and "·" in token:
                    # 解析记忆数等
                    continue
                full_text += token

            # 渲染气泡
            _render_echo_message(echo, full_text, tool_calls, 0, 0)

    except KeyboardInterrupt:
        console.print("\n  [yellow]⊘ 中断[/]")
    except EOFError:
        pass
    finally:
        with console.status("[dim]回响整理记忆中 …[/]", spinner="dots"):
            echo.sleep()
        console.print("[dim]  已退出[/]")


if __name__ == "__main__":
    main()
