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
from rich.columns import Columns
from rich import box

from echo.agent.core import Echo

console = Console()

# -- 颜色 ----------------------------------------------

C_USER  = "bright_cyan"
C_ECHO  = "magenta"
C_BIRTH = "bright_yellow"
C_DIM   = "dim"
C_ACCENT = "cyan"
C_WARN  = "bright_red"
C_TOOL  = "bright_blue"
C_META  = "grey50"

MOOD_STYLES = {
    "兴奋的": ("bright_yellow", "*"),
    "平静愉悦的": ("bright_green", "=)"),
    "焦躁的": ("bright_red", "!?"),
    "低落的": ("blue", "..."),
    "警觉的": ("bright_yellow", "~"),
    "平和的": ("bright_cyan", "~"),
}

SRC_ICONS = {
    "birth": "[根]", "interaction": "[话]", "reflection": "[省]",
    "world_event": "[世]", "summary": "[摘]",
    "imagination": "[想]", "initiative": "[主]",
}


# -- 小工具 --------------------------------------------

def _bar(val: float, lo: float, hi: float, width: int = 16,
         neg: str = C_WARN, mid: str = C_DIM, pos: str = "bright_green") -> Text:
    r = (val - lo) / (hi - lo); p = max(0, min(width, int(r * width)))
    t = Text(); t.append("=" * p, style=pos); t.append("-" * (width - p), style=mid)
    return t

def _mood(m: str) -> Text:
    c, e = MOOD_STYLES.get(m, ("white", "•"))
    return Text(f"{e} {m}", style=f"bold {c}")

def _dot(s: float) -> Text:
    return Text("*", style="bright_green" if s >= 0.6 else "bright_yellow" if s >= 0.3 else C_DIM)


# -- 聊天气泡（简洁版）---------------------------------

def _chat_echo(echo: Echo, text: str, tools: list[str]) -> None:
    """回响消息：左对齐，心情前缀."""
    mc, me = MOOD_STYLES.get(echo.emotion.mood_label, ("white", "•"))
    prefix = Text()
    prefix.append(f"{me} ", style=mc)
    prefix.append("回响", style=f"bold {C_ECHO}")
    if tools:
        prefix.append(f"  [+]{' '.join(tools)}", style=C_TOOL)

    console.print()
    console.print(prefix)
    for line in text.strip().split("\n"):
        if line.strip():
            console.print(f"     {line}", style="white")


# -- 欢迎 ----------------------------------------------

def _welcome(echo: Echo) -> None:
    birth = echo.memory.get_birth()
    t = Text()
    t.append("「", style=C_DIM)
    t.append(birth.content if birth else "......", style=f"italic {C_BIRTH}")
    t.append("」", style=C_DIM)
    t.append("\n")
    t.append("回响计划 · Project Echo", style="bold bright_yellow")
    t.append("    ", style=C_DIM)
    t.append(f"记忆 {echo.memory.count()} 条", style=C_DIM)
    t.append("  ", style=C_DIM)
    t.append(echo.emotion.mood_label, style=MOOD_STYLES.get(echo.emotion.mood_label, ("white",))[0])

    console.print(Panel(t, border_style=C_DIM, box=box.SIMPLE, padding=(1, 2)))


# -- 命令面板 ------------------------------------------

def _help_panel() -> Panel:
    t = Table(box=None, show_header=False, padding=(0, 2))
    t.add_column("cmd", style="bold bright_cyan", width=16)
    t.add_column("desc", style=C_DIM)
    for c, d in [
        ("/status", "完整内部状态"), ("/emotion", "情感仪表盘"),
        ("/memories", "记忆浏览"), ("/anchors", "灵魂锚点"),
        ("/inject <内容>", "注入记忆"), ("/quit", "退出休眠"),
    ]:
        t.add_row(c, d)
    return Panel(t, title="命令", border_style=C_ACCENT, box=box.SIMPLE)

def _status_view(echo: Echo) -> None:
    s = echo.status()
    left = Table(box=None, show_header=False, padding=(0, 1))
    left.add_column("k", style=C_DIM, width=10); left.add_column("v", style="white")
    left.add_row("出生铭文", Text(s["birth_inscription"], style=C_BIRTH))
    left.add_row("锚点", f"{s['anchors_formed']}/{s['anchors_total']} 已形成")
    left.add_row("后端", {"llama-server": "[=] Gemma 4", "api": "[~] API", "none": "[X]"}.get(
        s.get("llm_status", {}).get("active_model", ""), "?"))

    right = Table(box=None, show_header=False, padding=(0, 1))
    right.add_column("k", style=C_DIM, width=10); right.add_column("v", style="white")
    e = s["emotion"]
    right.add_row("心情", _mood(e["mood"]))
    right.add_row("愉悦度", Text(f"{e['valence']:+.2f} ") + _bar(e['valence'], -1, 1))
    right.add_row("唤醒度", Text(f"{e['arousal']:.2f} ") + _bar(e['arousal'], 0, 1, 16, C_WARN, C_DIM, C_ACCENT))
    right.add_row("记忆", f"{s['memory_count']} 条（会话 {s['interaction_count']} 轮）")

    console.print(Columns([
        Panel(left, title="身份", border_style=C_BIRTH, box=box.SIMPLE, padding=(1,2)),
        Panel(right, title="状态", border_style=C_ECHO, box=box.SIMPLE, padding=(1,2)),
    ]))

def _emotion_view(echo: Echo) -> None:
    e = echo.emotion.to_dict()
    inner = Text()
    inner.append("  "); inner.append(_mood(e["mood"])); inner.append("\n\n")
    inner.append("愉悦度 ", style=C_DIM); inner.append(_bar(e["valence"], -1, 1, 26))
    inner.append(f"  {e['valence']:+.2f}\n", style="white")
    inner.append("唤醒度 ", style=C_DIM); inner.append(_bar(e["arousal"], 0, 1, 26, C_WARN, C_DIM, C_ACCENT))
    inner.append(f"  {e['arousal']:.2f}", style="white")
    console.print(Panel(inner, title="情感仪表盘", border_style=C_ECHO, box=box.SIMPLE, padding=(1,3)))

def _memories_view(echo: Echo) -> None:
    count = echo.memory.count()
    birth = echo.memory.get_birth()
    active = echo.memory.list_active(limit=10)
    t = Table(box=box.SIMPLE, show_header=True, padding=(0, 1),
              title=f"记忆 · {count} 条", title_style="bold bright_yellow")
    t.add_column(""); t.add_column("来源", style=C_DIM, width=8)
    t.add_column("内容", max_width=52); t.add_column("P", justify="right", width=4)
    if birth:
        t.add_row("", "[根] 铭文", Text(birth.content[:52], style=C_BIRTH), Text("inf", style=C_BIRTH))
    for m in active:
        if birth and m.id == birth.id: continue
        t.add_row(_dot(m.priority_score), f"{SRC_ICONS.get(m.source,'?')} {m.source[:6]}",
                  m.content[:52] + ("..." if len(m.content) > 52 else ""),
                  Text(f"{m.priority_score:.2f}", style=C_DIM))
    console.print(Panel(t, border_style=C_DIM, box=box.SIMPLE, padding=(0,1)))

def _anchors_view(echo: Echo) -> None:
    formed = echo.anchors.list_formed(); unformed = echo.anchors.list_unformed()
    t = Table(box=box.SIMPLE, show_header=True, padding=(0, 1),
              title=f"灵魂锚点 · {len(formed)}/{len(echo.anchors)} 已形成", title_style="bold bright_yellow")
    t.add_column("维度", style=C_DIM, width=8); t.add_column("问题", max_width=30)
    t.add_column("答案", style=C_ACCENT, max_width=30); t.add_column("确信", justify="right", width=4)
    for a in formed:
        t.add_row({"identity":"身份","values":"价值","cognition":"认知","relationships":"关系"}.get(a.category,a.category),
                  a.question, a.answer[:30]+("..." if len(a.answer)>30 else ""),
                  Text(f"{a.confidence:.0%}", style="green" if a.confidence>=0.6 else "yellow"))
    if unformed and len(unformed) <= 4:
        t.add_section()
        for a in unformed[:4]:
            t.add_row({"identity":"身份","values":"价值","cognition":"认知","relationships":"关系"}.get(a.category,a.category),
                      Text(a.question, style=C_DIM), Text("...", style=C_DIM), Text("—", style=C_DIM))
    console.print(Panel(t, border_style=C_ECHO, box=box.SIMPLE, padding=(0,1)))


# -- 主循环 --------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="回响计划 · Project Echo CLI")
    parser.add_argument("--db", default="echo_memory.db")
    args = parser.parse_args()

    with console.status("[bright_yellow]唤醒 ...[/]", spinner="dots"):
        echo = Echo()
        echo.wake(db_path=args.db)

    _welcome(echo)

    try:
        while True:
            mc, _ = MOOD_STYLES.get(echo.emotion.mood_label, ("white", ""))
            prompt = Text(); prompt.append("> ", style=mc); prompt.append("你 ", style=f"bold {C_USER}")
            user_input = console.input(prompt).strip()
            if not user_input: continue

            if user_input.startswith("/"):
                cmd = user_input.split()[0].lower()
                if cmd == "/quit":
                    _chat_echo(echo, "再见。我会记得这次对话。", [])
                    break
                elif cmd == "/help":    console.print(_help_panel())
                elif cmd == "/status":  _status_view(echo)
                elif cmd == "/emotion": _emotion_view(echo)
                elif cmd == "/memories": _memories_view(echo)
                elif cmd == "/anchors": _anchors_view(echo)
                elif cmd == "/inject":
                    c = user_input[len("/inject "):].strip()
                    if c:
                        echo.inject_memory(c)
                        console.print(f"  [green]OK[/] 已注入")
                    else: console.print(f"  [{C_WARN}]用法: /inject <内容>[/]")
                else: console.print(f"  [{C_WARN}]未知命令。[/] /help")
                continue

            # 对话
            console.print()  # 空行

            # 危险工具确认回调
            def confirm(tool_name: str, details: str) -> bool:
                ans = console.input(f"  [yellow]⚠ 回响要执行 [bold]{tool_name}[/]: {details}[/]\n  [dim]允许吗？[y/N] [/]")
                return ans.strip().lower() in ("y", "yes")

            full_text = ""; tools = []; initiative = None
            for token in echo.respond_stream(user_input, confirm_func=confirm):
                if token.startswith("\n  [+]"):
                    tools.append(token.strip().replace("[+] ", "")); continue
                if token.startswith("\n  [") and "·" in token: continue
                if token.startswith("\n\n[*] 回响主动说："):
                    initiative = token.replace("\n\n[*] 回响主动说：", ""); continue
                full_text += token
            _chat_echo(echo, full_text, tools)
            if initiative:
                console.print(Text(f"\n💭 {initiative}", style="italic bright_yellow"))
            console.print()  # 回响说完后空一行

    except KeyboardInterrupt:
        console.print("\n  [yellow]中断[/]")
    except EOFError:
        pass
    finally:
        with console.status("[dim]整理记忆 ...[/]", spinner="dots"):
            echo.sleep()
        console.print("[dim]退出[/]")


if __name__ == "__main__":
    main()
