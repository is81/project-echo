"""回响计划 · CLI 交互界面.

Usage:
    python -m echo.cli
    python -m echo.cli --db echo_memory.db
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.live import Live
from rich.layout import Layout
from rich import box

from echo.agent.core import Echo

console = Console()

# ── 颜色主题 ──────────────────────────────────────────
C_USER = "bright_cyan"
C_ECHO = "bright_magenta"
C_BIRTH = "yellow"
C_MOOD = "green"
C_DIM = "dim"
C_ACCENT = "cyan"
C_WARN = "red"

# 心情 → (颜色, emoji)
MOOD_STYLES = {
    "兴奋的":   ("bright_yellow", "✨"),
    "平静愉悦的": ("green",         "😌"),
    "焦躁的":   ("red",           "😤"),
    "低落的":   ("blue",          "😔"),
    "警觉的":   ("yellow",        "🧐"),
    "平和的":   ("bright_cyan",   "🧘"),
}


def _mood_display(mood: str) -> Text:
    """返回带颜色+emoji的心情文本."""
    color, emoji = MOOD_STYLES.get(mood, ("white", ""))
    return Text(f"{emoji}  {mood}", style=color)


def _valence_bar(valence: float) -> Text:
    """将 valence [-1,1] 渲染为彩色小条."""
    width = 20
    # 映射 [-1, 1] → [0, width]
    pos = int((valence + 1) / 2 * width)
    pos = max(0, min(width, pos))
    bar = ""
    for i in range(width):
        if i < pos:
            bar += "█"
        else:
            bar += "░"
    if valence < -0.3:
        color = "red"
    elif valence > 0.3:
        color = "green"
    else:
        color = "dim"
    return Text(bar, style=color)


def _arousal_bar(arousal: float) -> Text:
    """将 arousal [0,1] 渲染为彩色小条."""
    width = 20
    pos = int(arousal * width)
    pos = max(0, min(width, pos))
    bar = "█" * pos + "░" * (width - pos)
    if arousal > 0.6:
        color = "bright_yellow"
    elif arousal > 0.3:
        color = "cyan"
    else:
        color = "blue"
    return Text(bar, style=color)


def _banner() -> Panel:
    """渲染启动横幅."""
    title = Text("回响计划 · Project Echo", style="bold bright_yellow")
    body = Text()
    body.append("一个带有深度记忆、性格演化和叙事感的交互式存在体\n", style=C_DIM)
    body.append("\n")
    body.append("/status   ", style="bright_cyan")
    body.append("内部状态    ", style=C_DIM)
    body.append("/emotion  ", style="bright_cyan")
    body.append("情感状态\n", style=C_DIM)
    body.append("/memories ", style="bright_cyan")
    body.append("记忆浏览    ", style=C_DIM)
    body.append("/help     ", style="bright_cyan")
    body.append("命令列表\n", style=C_DIM)
    body.append("/quit     ", style="bright_cyan")
    body.append("退出对话", style=C_DIM)
    return Panel(body, title=title, border_style="bright_yellow", padding=(1, 2))


def _help_panel() -> Panel:
    """渲染帮助面板."""
    body = Text()
    body.append("/status\n", style="bright_cyan")
    body.append("  查看回响的完整内部状态（静默观察模式）\n\n", style=C_DIM)
    body.append("/emotion\n", style="bright_cyan")
    body.append("  查看当前情感：愉悦度、唤醒度、心情\n\n", style=C_DIM)
    body.append("/memories\n", style="bright_cyan")
    body.append("  浏览记忆：总数、出生铭文、最近活跃记忆\n\n", style=C_DIM)
    body.append("/inject <内容>\n", style="bright_cyan")
    body.append("  手动注入一条记忆（调试用）\n\n", style=C_DIM)
    body.append("/quit\n", style="bright_cyan")
    body.append("  退出对话，回响将休眠", style=C_DIM)
    return Panel(body, title="可用命令", border_style="bright_cyan", padding=(1, 2))


def _status_table(echo: Echo) -> Table:
    """渲染状态表格."""
    s = echo.status()
    table = Table(box=box.ROUNDED, border_style=C_DIM, show_header=False,
                  title="回响内部状态", title_style="bold yellow")
    table.add_column("项目", style="bright_cyan", width=20)
    table.add_column("值", style="white")

    llm = s.get("llm_status", {})
    active = llm.get("active_model", "none")
    active_str = {"llama-server": "🖥️  本地 Gemma 4", "api": "☁️  云端 API", "none": "❌ 无"}.get(active, active)

    rows = [
        ("版本", s["version"]),
        ("出生铭文", Text(s["birth_inscription"], style=C_BIRTH)),
        ("总记忆数", str(s["memory_count"])),
        ("本轮对话数", str(s["interaction_count"])),
        ("心情", _mood_display(s["emotion"]["mood"])),
        ("愉悦度", _valence_bar(s["emotion"]["valence"])),
        ("唤醒度", _arousal_bar(s["emotion"]["arousal"])),
        ("LLM 后端", active_str),
        ("基因原则", f"{s['principles_count']} 条"),
    ]
    for label, value in rows:
        table.add_row(label, value)
    return table


def _emotion_panel(echo: Echo) -> Panel:
    """渲染情感面板."""
    e = echo.emotion.to_dict()
    body = Text()
    body.append(_mood_display(e["mood"]))
    body.append("\n\n")
    body.append("愉悦度 ", style=C_DIM)
    body.append(_valence_bar(e["valence"]))
    body.append(f"  {e['valence']:+.2f}\n", style="white")
    body.append("唤醒度 ", style=C_DIM)
    body.append(_arousal_bar(e["arousal"]))
    body.append(f"  {e['arousal']:.2f}", style="white")
    return Panel(body, title="情感状态", border_style="bright_magenta", padding=(1, 2))


def _memories_table(echo: Echo) -> Table:
    """渲染记忆浏览表格."""
    count = echo.memory.count()
    birth = echo.memory.get_birth()
    active = echo.memory.list_active(limit=10)

    table = Table(box=box.ROUNDED, border_style=C_DIM, show_header=True,
                  title=f"记忆浏览（共 {count} 条）", title_style="bold yellow")
    table.add_column("来源", style=C_DIM, width=12)
    table.add_column("内容", style="white", max_width=55)
    table.add_column("权重", style="bright_cyan", width=8)

    if birth:
        table.add_row(
            Text("🏠 出生铭文", style=C_BIRTH),
            Text(birth.content, style=C_BIRTH),
            Text("1.00", style="green"),
        )

    for m in active:
        if birth and m.id == birth.id:
            continue
        src_icon = {"interaction": "💬", "reflection": "🪞", "world_event": "🌍",
                    "summary": "📝"}.get(m.source, "❓")
        table.add_row(
            f"{src_icon} {m.source}",
            m.content[:55] + ("..." if len(m.content) > 55 else ""),
            f"{m.base_weight:.2f}",
        )
    return table


def main():
    parser = argparse.ArgumentParser(description="回响计划 · Project Echo CLI")
    parser.add_argument(
        "--db", default="echo_memory.db", help="记忆数据库路径 (默认: echo_memory.db)"
    )
    args = parser.parse_args()

    # 唤醒
    with console.status("[yellow]唤醒回响中...[/]", spinner="dots"):
        echo = Echo()
        echo.wake(db_path=args.db)

    # 出生铭文
    birth = echo.memory.get_birth()
    if birth:
        console.print(Panel(
            Text(f"「{birth.content}」", style=C_BIRTH),
            title="出生铭文",
            border_style=C_BIRTH,
        ))

    console.print(_banner())

    try:
        while True:
            user_input = console.input(f"\n[bold {C_USER}]你[/]: ").strip()

            if not user_input:
                continue

            # 命令处理
            if user_input.startswith("/"):
                cmd = user_input.split()
                cmd_name = cmd[0].lower()

                if cmd_name == "/quit":
                    console.print(f"[{C_ECHO}]回响[/]: 再见。我会记得这次对话。")
                    break
                elif cmd_name == "/help":
                    console.print(_help_panel())
                elif cmd_name == "/status":
                    console.print(_status_table(echo))
                elif cmd_name == "/emotion":
                    console.print(_emotion_panel(echo))
                elif cmd_name == "/memories":
                    console.print(_memories_table(echo))
                elif cmd_name == "/inject":
                    content = user_input[len("/inject "):].strip()
                    if content:
                        mem_id = echo.inject_memory(content)
                        console.print(f"[green]✓[/] 记忆已注入: [{C_DIM}]{mem_id[:12]}...[/]")
                    else:
                        console.print(f"[{C_WARN}]用法: /inject <内容>[/]")
                else:
                    console.print(f"[{C_WARN}]未知命令: {cmd_name}。输入 /help 查看可用命令。[/]")
                continue

            # 流式对话
            console.print()  # 空行
            mood_color, _ = MOOD_STYLES.get(echo.emotion.mood_label, ("white", ""))
            console.print(f"[bold {C_ECHO}]回响[/] [dim {mood_color}]· {echo.emotion.mood_label}[/] ")

            first_token = True
            for token in echo.respond_stream(user_input):
                if first_token:
                    first_token = False
                console.print(token, end="", highlight=False)
            console.print()  # 换行

    except KeyboardInterrupt:
        console.print("\n[yellow]收到中断信号...[/]")
    except EOFError:
        pass
    finally:
        console.print("[dim]回响休眠中...[/]")
        echo.sleep()
        console.print("[dim]已退出。[/]")


if __name__ == "__main__":
    main()
