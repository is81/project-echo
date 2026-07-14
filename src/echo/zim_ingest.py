"""ZIM → Echo 记忆导入管道.

提供:
  - 预定义话题 → 关键词映射
  - 分类发现（扫描 V namespace）
  - 批量导入管道（分类筛选 + HTML→文本 + bulk_insert）

Usage:
    from echo.zim_ingest import discover_categories_from_zim, ingest_zim_to_echo
"""

import time
from pathlib import Path
from typing import Optional

from echo.memory.models import Memory
from echo.zim_reader import ZimReader


# ── 预定义话题 → 中文关键词 ─────────────────────────────

TOPIC_KEYWORDS: dict[str, list[str]] = {
    "computer": [
        "计算机", "编程", "软件", "算法", "人工智能", "机器学习",
        "网络", "数据库", "操作系统", "密码学", "数据结构",
        "编程语言", "编译器", "互联网", "电脑", "处理器",
        "深度学习", "神经网络", "自然语言处理", "计算机视觉",
        "软件工程", "前端", "后端", "云计算", "分布式",
        "信息安全", "网络安全", "计算机科学",
    ],
    "philosophy": [
        "哲学", "伦理学", "形而上学", "认识论", "逻辑学",
        "美学", "存在主义", "现象学", "儒家", "道家",
    ],
    "science": [
        "物理", "化学", "生物", "数学", "天文", "地理",
        "量子力学", "相对论", "进化", "基因", "细胞",
    ],
    "history": [
        "历史", "朝代", "战争", "文明", "古代", "帝国",
        "革命", "王朝", "考古",
    ],
    "art": [
        "艺术", "绘画", "音乐", "文学", "电影", "雕塑",
        "诗歌", "小说", "戏剧", "建筑",
    ],
}


def resolve_keywords(topic: str) -> list[str]:
    """解析话题参数 → 关键词列表.

    支持预定义话题名（如 "computer"）和自定义关键词（逗号分隔）。
    """
    topic = topic.strip()
    if not topic:
        return []

    # 尝试匹配预定义话题
    lowered = topic.lower()
    if lowered in TOPIC_KEYWORDS:
        return TOPIC_KEYWORDS[lowered]

    # 当作自定义关键词（逗号分隔）
    return [kw.strip() for kw in topic.split(",") if kw.strip()]


# ── 分类发现 ────────────────────────────────────────────

def discover_categories_from_zim(
    zim_path: str | Path,
    keywords: list[str],
) -> list:
    """扫描 ZIM 文件中的匹配分类.

    Args:
        zim_path: ZIM 文件路径
        keywords: 中文关键词列表

    Returns:
        list[CategoryInfo]: 匹配的分类列表
    """
    with ZimReader(zim_path) as reader:
        reader.open()
        categories = reader.discover_categories(keywords)

    return categories


# ── 导入管道 ────────────────────────────────────────────

def ingest_zim_to_echo(
    echo,
    zim_path: str | Path,
    mode: str = "first_para",
    max_articles: int = 0,
    batch_size: int = 5000,
    keywords: Optional[list[str]] = None,
    dry_run: bool = False,
    console=None,
) -> dict:
    """将 ZIM 文件中的文章导入 Echo 记忆库.

    Args:
        echo: Echo 实例（已 wake）
        zim_path: ZIM 文件路径
        mode: "titles" | "first_para" | "full"
        max_articles: 最多导入文章数（0 = 不限）
        batch_size: 每批提交数
        keywords: 分类筛选关键词列表（None = 导入全部文章）
        dry_run: True = 只扫描不导入
        console: Rich Console 实例（用于进度显示）

    Returns:
        {"total_categories": N, "total_article_ids": N,
         "imported": N, "skipped": N, "duration_sec": float}
    """
    start_time = time.time()
    zim_path = Path(zim_path)

    stats = {
        "total_categories": 0,
        "total_article_ids": 0,
        "imported": 0,
        "skipped": 0,
        "duration_sec": 0.0,
    }

    with ZimReader(zim_path) as reader:
        reader.open()

        # ── 打印 ZIM 信息 ──
        if console:
            console.print(f"[dim]ZIM 后端: {reader.backend_name}[/]")
            console.print(f"[dim]文章总数: {reader.article_count:,}")
            console.print(f"[dim]V namespace 分类: {'有' if reader.has_category_support else '无'}[/]")

        # ── 确定文章源 ──
        article_ids_set: set[int] = set()
        use_title_filter = False

        if keywords:
            if reader.has_category_support:
                # 策略 A: V namespace 分类筛选
                if console:
                    with console.status("[cyan]扫描 V namespace 分类...[/]"):
                        categories = reader.discover_categories(keywords)
                else:
                    categories = reader.discover_categories(keywords)

                stats["total_categories"] = len(categories)

                if console:
                    if categories:
                        console.print(f"\n[bold]匹配到 {len(categories)} 个分类:[/]")
                        for cat in categories:
                            console.print(
                                f"  [cyan]{cat.name}[/] — "
                                f"[dim]{cat.article_count:,} 篇文章[/]"
                            )
                    else:
                        console.print("[yellow]V namespace 中未找到匹配分类[/]")

                for cat in categories:
                    article_ids_set.update(cat.article_ids)

                stats["total_article_ids"] = len(article_ids_set)

            if not article_ids_set:
                # 策略 B: 标题关键词匹配（V namespace 不可用或没匹配到）
                use_title_filter = True
                if console:
                    mode_label = "回退到" if reader.has_category_support else "使用"
                    console.print(
                        f"\n[cyan]{mode_label}标题关键词扫描"
                        f"（{len(keywords)} 个关键词）...[/]"
                    )

                if dry_run:
                    # Dry-run: 只扫描标题，收集 entry_id
                    matched = reader.discover_by_title(keywords)
                    article_ids_set = {eid for eid, _ in matched}
                    stats["total_article_ids"] = len(article_ids_set)

                    if console:
                        console.print(
                            f"[bold]标题匹配到 {len(matched):,} 篇文章[/]"
                        )
                        # 显示前 20 个匹配标题
                        for _, title in matched[:20]:
                            console.print(f"  [dim]{title}[/]")
                        if len(matched) > 20:
                            console.print(f"  [dim]... 还有 {len(matched) - 20} 篇[/]")
                else:
                    # 非 dry-run：流式迭代（无需预先收集 ID）
                    stats["total_article_ids"] = 0  # 流式，提前无法知道总数
            elif console and article_ids_set:
                console.print(
                    f"\n[bold]去重后共 {len(article_ids_set):,} 篇文章[/]"
                )
        else:
            # 无关键词 → 全量导入（仅限 --max-articles）
            if console:
                console.print(
                    "[yellow]未指定 --zim-topic，将迭代全部文章（不推荐）[/]"
                )

        # ── dry-run 模式：到此为止 ──
        if dry_run:
            stats["duration_sec"] = time.time() - start_time
            if console:
                console.print(
                    f"\n[green]Dry-run 完成[/] "
                    f"({stats['duration_sec']:.1f}s)"
                )
            return stats

        # ── 构建并导入 ──
        batch: list[Memory] = []
        total_processed = 0

        # 选择迭代器
        if use_title_filter:
            article_iter = reader.iter_by_title_filter(
                keywords, max_articles=max_articles,
            )
        elif article_ids_set:
            article_iter = reader.get_articles_by_ids(
                list(article_ids_set), max_articles=max_articles,
            )
        else:
            article_iter = reader.iter_articles(
                namespaces=["A"], max_articles=max_articles,
            )

        if console:
            console.print(f"[dim]开始导入... 每批 {batch_size} 条[/]")

        for article in article_iter:
            if max_articles > 0 and total_processed >= max_articles:
                break

            # 构建内容
            content = _build_memory_content(article.title, article.text, mode)
            if not content.strip():
                continue

            # 构建 Memory
            tags = ["wikipedia", "zim"]
            mem = Memory(
                content=content,
                source="learned",
                tags=tags,
                base_weight=0.3,        # 低于对话记忆，避免挤占
                emotional_valence=0.0,
                emotional_arousal=0.1,
            )
            batch.append(mem)
            total_processed += 1

            # 批量提交
            if len(batch) >= batch_size:
                inserted = echo.memory.bulk_insert(batch)
                stats["imported"] += inserted
                stats["skipped"] += len(batch) - inserted
                batch.clear()

                if console:
                    console.print(
                        f"  [dim]已处理 {total_processed:,} 篇"
                        f"（新增 {inserted}）...[/]"
                    )

        # 提交剩余批次
        if batch:
            inserted = echo.memory.bulk_insert(batch)
            stats["imported"] += inserted
            stats["skipped"] += len(batch) - inserted

        # 统一重算优先级
        if console:
            with console.status("[dim]重算优先级...[/]"):
                echo.memory._recalc_all_priorities()
        else:
            echo.memory._recalc_all_priorities()

    stats["duration_sec"] = time.time() - start_time
    return stats


# ── 内容构建 ────────────────────────────────────────────

def _build_memory_content(title: str, text: str, mode: str) -> str:
    """按模式构建记忆内容.

    Args:
        title: 文章标题
        text: 已剥离 HTML 的纯文本
        mode: "titles" | "first_para" | "full"
    """
    prefix = f"[Wikipedia] {title}"

    if mode == "titles":
        first_sentence = _extract_first_sentence(text)
        return f"{prefix}\n{first_sentence}"

    elif mode == "first_para":
        first_para = _extract_first_paragraph(text, title)
        if not first_para:
            first_para = _extract_first_sentence(text)
        return f"{prefix}\n{first_para}"

    elif mode == "full":
        truncated = text[:2000]
        if len(text) > 2000:
            truncated += "..."
        return f"{prefix}\n{truncated}"

    else:
        return f"{prefix}\n{text[:500]}"


def _extract_first_paragraph(text: str, title: str = "") -> str:
    """从维基百科纯文本中提取第一个有实质内容的段落.

    跳过仅含标题的块、空白块和 wiki 元信息。
    """
    if not text:
        return ""

    # 按空行分割段落
    blocks = text.split("\n\n")

    for block in blocks:
        block = block.strip()
        if not block:
            continue
        # 跳过只含标题的行
        if block == title.strip():
            continue
        # 跳过明显是导航/元信息的行
        if block in ("维基百科，自由的百科全书", "维基百科"):
            continue
        # 跳过太短的块
        if len(block) < 10:
            continue
        # 找到了第一个实质性段落
        return block

    # 都太短，返回最长的那个
    longest = max((b.strip() for b in blocks if b.strip()), key=len, default="")
    return longest


def _extract_first_sentence(text: str) -> str:
    """从文本中提取第一句话."""
    if not text:
        return ""

    # 按中英文标点分割
    for i, ch in enumerate(text):
        if ch in ("。", "！", "？", ".", "!", "?", "\n"):
            return text[:i + 1].strip()
    return text[:200].strip()
