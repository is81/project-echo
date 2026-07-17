"""回响计划 · CLI 交互界面.

Usage:
    python -m echo.cli
    python -m echo.cli --db echo_memory.db
"""

import argparse
import msvcrt
import sys
import time
from datetime import datetime
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
    "procedural": "[习]",
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

    # 六模块信息
    critique_s = s.get("critique", {})
    if critique_s:
        total_r = critique_s.get("total_reviews", 0)
        pass_r = critique_s.get("pass_rate", 1.0)
        right.add_row("审查", f"{total_r}次 · {pass_r:.0%} 通过" if total_r > 0 else "审查", style=C_DIM)

    bus_modules = s.get("bus_modules", [])
    if bus_modules:
        enabled_count = sum(1 for m in bus_modules if m.get("enabled"))
        right.add_row("模块总线", f"{enabled_count}/{len(bus_modules)} 模块活跃")

    mod_params = s.get("module_params", {})
    if mod_params:
        right.add_row("调制", f"审查{mod_params.get('review_strictness', 1.0):.2f}× "
                            f"规划{mod_params.get('planning_aggressiveness', 1.0):.2f}×")

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


# -- 探索模式 ------------------------------------------

def _run_explore_mode(echo, interval_min: int = 10, max_rounds: int = 0,
                     topics: list[str] | None = None) -> None:
    """探索模式：回响自主选择话题、搜索、学习、思考。

    不参与对话，自己在网络上游荡，把学到的东西存入记忆。
    直到 Ctrl+C 或达到指定轮数。

    Args:
        topics: 可选，指定探索话题列表。为空时回响自己选。
    """
    import time

    topics = topics or []
    topic_mode = "指定话题" if topics else "自主选择"
    desc = (
        f"探索模式 · 每 {interval_min} 分钟探索一个话题 · {topic_mode}\n"
        f"回响会搜索、学习、存入记忆"
    )
    if topics:
        desc += f"\n话题列表: {', '.join(topics)}"
    desc += "\n按 Ctrl+C 退出"

    console.print(Panel(Text(desc, style=C_DIM),
                 border_style=C_ACCENT, box=box.SIMPLE, padding=(1, 2)))

    _welcome(echo)

    topic_idx = 0  # 指定话题时的游标
    round_num = 0
    try:
        while True:
            round_num += 1
            if max_rounds > 0 and round_num > max_rounds:
                break

            # 分隔线
            t = Text()
            t.append(f"── 第 {round_num} 轮探索 ", style=C_DIM)
            t.append(datetime.now().strftime("%H:%M:%S"), style=C_META)
            if max_rounds > 0:
                t.append(f" /{max_rounds}", style=C_META)
            t.append(" ──", style=C_DIM)
            console.print()
            console.print(t)

            # 确定本轮话题
            current_topic = None
            if topics:
                current_topic = topics[topic_idx % len(topics)]
                topic_idx += 1
                console.print(f"  [dim]话题: {current_topic}[/]", style=C_DIM)

            # 执行探索
            result = echo.idle_explore(topic=current_topic)
            if result:
                console.print(f"  [green]=)[/] {result}", style="white")
            else:
                console.print(f"  [yellow]~[/] 没有结果，等待下一轮...", style=C_DIM)

            # 等待下一轮
            console.print(f"  [dim]下次探索: {interval_min} 分钟后[/]", style=C_META)
            try:
                time.sleep(interval_min * 60)
            except KeyboardInterrupt:
                break

    except KeyboardInterrupt:
        console.print()
    finally:
        with console.status("[dim]整理记忆 ...[/]", spinner="dots"):
            echo.sleep()
        console.print(f"[dim]探索 {round_num} 轮后退出[/]")

# -- 空闲主动说话 --------------------------------------

def _input_with_idle(echo, prompt_text: str, idle_seconds: int = 120):
    """轮询式输入，支持空闲检测。

    每 100ms 检查键盘输入。
    空闲超过 idle_seconds 时触发 echo.idle_initiate()。
    每 30 秒执行一次情绪衰减。

    非 TTY（管道/重定向）时回退到标准 input()。

    Returns:
        (user_input: str | None, initiative: str | None)
    """
    # 非 TTY 环境（管道/重定向）：回退到普通 input()
    if not sys.stdin.isatty():
        user_input = console.input(prompt_text).strip()
        return user_input, None

    # 渲染 prompt
    console.print(prompt_text, end="")
    sys.stdout.flush()

    buffer: list[str] = []
    last_activity = time.time()
    last_emotion_decay = time.time()
    idle_triggered = False
    EMOTION_DECAY_INTERVAL = 30  # 每 30 秒衰减一次

    def _redraw_prompt():
        """清除当前行并重绘提示符和已输入文字."""
        # 回到行首，清除到行尾
        sys.stdout.write("\r\033[K")
        sys.stdout.flush()
        console.print(prompt_text, end="")
        if buffer:
            sys.stdout.write("".join(buffer))
        sys.stdout.flush()

    while True:
        if msvcrt.kbhit():
            ch = msvcrt.getwch()

            if ch == "\r":  # Enter
                console.print()  # 换行
                return "".join(buffer).strip(), None
            elif ch == "\x08":  # Backspace
                if buffer:
                    buffer.pop()
                    _redraw_prompt()
                idle_triggered = False
                last_activity = time.time()
            elif ch == "\x03":  # Ctrl+C
                console.print()
                raise KeyboardInterrupt
            elif ch == "\x1a":  # Ctrl+Z (EOF)
                raise EOFError
            elif ch == "\x1b":  # Escape — 忽略（可能有后续序列）
                pass
            elif ch == "\xe0":  # 方向键前缀 — 读取下一个字符并忽略
                try:
                    msvcrt.getwch()
                except Exception:
                    pass
            elif ord(ch) >= 32 or ch in ("\t",):  # 可打印字符或 Tab
                buffer.append(ch)
                sys.stdout.write(ch)
                sys.stdout.flush()
                idle_triggered = False
                last_activity = time.time()

        else:
            time.sleep(0.1)
            now = time.time()

            # 情绪衰减（每 30 秒）
            if now - last_emotion_decay >= EMOTION_DECAY_INTERVAL:
                echo.emotion.idle_regress(now - last_emotion_decay)
                last_emotion_decay = now

            # 空闲主动说话
            if not idle_triggered and buffer == [] and now - last_activity >= idle_seconds:
                initiative = echo.idle_initiate()
                if initiative:
                    idle_triggered = True
                    last_activity = time.time()
                    last_emotion_decay = time.time()
                    # 清除当前提示行，显示主动说话
                    sys.stdout.write("\r\033[K")
                    sys.stdout.flush()
                    _chat_idle_initiative(echo, initiative)
                    # 重绘提示符
                    _redraw_prompt()
                    return None, initiative


def _chat_idle_initiative(echo, text: str) -> None:
    """显示空闲主动说话气泡."""
    mc, _ = MOOD_STYLES.get(echo.emotion.mood_label, ("white", "•"))
    prefix = Text()
    prefix.append("💭 回响", style=f"bold {C_ECHO}")

    console.print()
    console.print(prefix)
    for line in text.strip().split("\n"):
        if line.strip():
            console.print(f"     {line}", style="white italic")
    console.print()


# -- 主循环 --------------------------------------------

def _run_zim_ingest(echo, zim_path: str, topic: str = "",
                    mode: str = "first_para", max_articles: int = 0,
                    batch_size: int = 5000, dry_run: bool = False) -> None:
    """ZIM 导入模式：扫描分类 → 导入记忆."""
    from echo.zim_ingest import resolve_keywords, ingest_zim_to_echo

    # 解析关键词
    keywords = resolve_keywords(topic) if topic else None

    if topic and keywords:
        console.print(f"[bold]话题: {topic}[/]")
        console.print(f"[dim]关键词: {', '.join(keywords[:15])}{'...' if len(keywords) > 15 else ''}[/]")

    console.print(f"[dim]模式: {mode}  批次大小: {batch_size:,}[/]")
    if dry_run:
        console.print("[yellow]Dry-run 模式 — 只扫描不导入[/]")
    console.print()

    # 执行导入
    stats = ingest_zim_to_echo(
        echo, zim_path,
        mode=mode,
        max_articles=max_articles,
        batch_size=batch_size,
        keywords=keywords,
        dry_run=dry_run,
        console=console,
    )

    # 汇总
    console.print()
    t = Table(title="导入结果", border_style=C_ACCENT, box=box.SIMPLE)
    t.add_column("指标", style=C_DIM)
    t.add_column("数值", style="bright_white", justify="right")
    if stats["total_categories"] > 0:
        t.add_row("匹配分类", f"{stats['total_categories']:,}")
    if stats["total_article_ids"] > 0:
        t.add_row("去重文章 ID", f"{stats['total_article_ids']:,}")
    if not dry_run:
        t.add_row("新导入", f"{stats['imported']:,}")
        t.add_row("跳过（重复）", f"{stats['skipped']:,}")
        t.add_row("记忆总数", f"{echo.memory.count():,}")
    t.add_row("耗时", f"{stats['duration_sec']:.1f}s")
    console.print(t)

    if not dry_run and stats["imported"] > 0:
        console.print(f"\n[green]=) 已导入 {stats['imported']:,} 篇 Wikipedia 文章到记忆库[/]")

    echo.sleep()


def main():
    parser = argparse.ArgumentParser(description="回响计划 · Project Echo CLI")
    parser.add_argument("--db", default="echo_memory.db")
    parser.add_argument("--explore", action="store_true",
                       help="探索模式：回响自主搜索、学习、思考（不交互）")
    parser.add_argument("--interval", type=int, default=10,
                       help="探索间隔（分钟），默认 10")
    parser.add_argument("--rounds", type=int, default=0,
                       help="探索轮数（0=无限循环）")
    parser.add_argument("--topic", type=str, default="",
                       help="指定探索话题（逗号分隔多个），如: --topic \"量子计算,AI意识\"")

    # ── ZIM 导入 ──
    parser.add_argument("--ingest-zim", type=str, metavar="PATH",
                       help="从 ZIM 文件导入内容到记忆库")
    parser.add_argument("--zim-topic", type=str, default="",
                       help="按话题筛选（预定义: computer/philosophy/science/history/art，或自定义关键词逗号分隔）")
    parser.add_argument("--zim-mode", type=str, default="first_para",
                       choices=["titles", "first_para", "full"],
                       help="导入模式（默认 first_para）")
    parser.add_argument("--zim-batch-size", type=int, default=5000,
                       help="每批提交数（默认 5000）")
    parser.add_argument("--zim-dry-run", action="store_true",
                       help="只扫描分类不导入")
    parser.add_argument("--max-articles", type=int, default=0,
                       help="最多导入/探索文章数（0=不限）")
    args = parser.parse_args()

    # 解析话题列表
    topics_list: list[str] = []
    if args.topic:
        topics_list = [t.strip() for t in args.topic.split(",") if t.strip()]

    with console.status("[bright_yellow]唤醒 ...[/]", spinner="dots"):
        echo = Echo()
        echo.wake(db_path=args.db)

    # ── ZIM 导入模式 ──
    if args.ingest_zim:
        _run_zim_ingest(
            echo, args.ingest_zim,
            topic=args.zim_topic,
            mode=args.zim_mode,
            max_articles=args.max_articles,
            batch_size=args.zim_batch_size,
            dry_run=args.zim_dry_run,
        )
        return

    # ── 探索模式 ──
    if args.explore:
        _run_explore_mode(echo, interval_min=args.interval,
                         max_rounds=args.rounds, topics=topics_list)
        return

    _welcome(echo)

    try:
        while True:
            mc, _ = MOOD_STYLES.get(echo.emotion.mood_label, ("white", ""))
            prompt = Text(); prompt.append("> ", style=mc); prompt.append("你 ", style=f"bold {C_USER}")

            user_input, idle_initiative = _input_with_idle(echo, prompt, idle_seconds=120)

            # 空闲主动说话
            if idle_initiative:
                # 不重置空闲计时器，继续等待用户输入
                continue

            if not user_input:
                continue

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
