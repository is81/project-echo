"""ZIM 文件读取器 — libzim 主选，zimply-core 备选.

提供:
  - ZimArticle 数据类
  - ZimReader: 打开/迭代/分类发现
  - _wiki_html_to_text(): HTML → 纯文本（零新依赖）

Usage:
    from echo.zim_reader import ZimReader

    with ZimReader("wikipedia_zh.zim") as reader:
        for article in reader.iter_articles(max_articles=100):
            print(article.title)
"""

import re
import struct
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterator, Optional


# ── 数据模型 ────────────────────────────────────────────

@dataclass
class ZimArticle:
    """一篇 ZIM 文章."""
    title: str
    url: str
    text: str               # HTML 剥离后的纯文本
    namespace: str           # "A" = 文章, "V" = 分类, "M" = 元数据
    mimetype: str = "text/html"
    entry_id: int = 0       # ZIM 内部条目 ID


@dataclass
class CategoryInfo:
    """ZIM 分类信息."""
    name: str               # 分类名，如 "Category:计算机科学"
    path: str               # ZIM 路径，如 "V/Category:计算机科学"
    article_count: int      # 该分类下的文章数
    article_ids: list[int] = field(default_factory=list)  # 文章条目 ID 列表


# ── HTML 剥离（零依赖）──────────────────────────────────

# 需要整块移除的标签（含内容）
_REMOVE_TAGS = ("script", "style", "nav", "table", "figure", "infobox",
                "footer", "header", "aside", "noscript", "math", "svg")

# 块级标签 → 换行
_BLOCK_TAGS = ("p", "h1", "h2", "h3", "h4", "h5", "h6",
               "div", "li", "br", "tr", "ul", "ol", "dl", "dd", "dt",
               "section", "article", "blockquote", "pre", "hr", "caption")


class _WikiHTMLStripper(HTMLParser):
    """stdlib HTMLParser 子类 —— 提取纯文本，跳过非内容标签."""

    def __init__(self):
        super().__init__()
        self._text: list[str] = []
        self._skip_depth = 0
        self._skip_tags: set[str] = set(_REMOVE_TAGS)

    def handle_starttag(self, tag, attrs):
        tag_lower = tag.lower()
        if tag_lower in self._skip_tags:
            self._skip_depth += 1
        elif tag_lower in _BLOCK_TAGS:
            self._text.append("\n")
        elif tag_lower == "a":
            # 链接只保留文字，不保留 href
            pass

    def handle_endtag(self, tag):
        tag_lower = tag.lower()
        if tag_lower in self._skip_tags:
            if self._skip_depth > 0:
                self._skip_depth -= 1
        elif tag_lower in _BLOCK_TAGS:
            self._text.append("\n")

    def handle_data(self, data):
        if self._skip_depth > 0:
            return
        self._text.append(data)

    def handle_entityref(self, name):
        # 处理 &amp; &lt; &gt; 等 HTML 实体
        if self._skip_depth > 0:
            return
        entities = {
            "amp": "&", "lt": "<", "gt": ">", "quot": '"', "apos": "'",
            "nbsp": " ", "mdash": "—", "ndash": "–", "ldquo": "“",
            "rdquo": "”", "lsquo": "‘", "rsquo": "’",
            "hellip": "…", "middot": "·",
        }
        self._text.append(entities.get(name, f"&{name};"))

    def get_text(self) -> str:
        return "".join(self._text)


def _wiki_html_to_text(html: str, max_chars: int = 0) -> str:
    """将维基百科 HTML 转为纯文本.

    Args:
        html: 原始 HTML 字符串
        max_chars: 最大字符数（0 = 不截断）

    Returns:
        剥离标签后的纯文本
    """
    if not html:
        return ""

    try:
        stripper = _WikiHTMLStripper()
        stripper.feed(html)
        text = stripper.get_text()
    except Exception:
        # HTMLParser 失败时回退到 regex
        text = _html_to_text_regex(html)

    # 折叠空白
    text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)  # 3+ 换行 → 2
    text = re.sub(r"[ \t]+", " ", text)             # 多空格 → 单空格
    text = re.sub(r" +\n", "\n", text)              # 行尾空格去掉
    text = text.strip()

    if max_chars > 0 and len(text) > max_chars:
        # 在最近一个换行或空格处截断
        cut = text.rfind("\n", 0, max_chars)
        if cut < max_chars // 2:
            cut = text.rfind(" ", 0, max_chars)
        if cut < max_chars // 2:
            cut = max_chars
        text = text[:cut].strip()

    return text


def _html_to_text_regex(html: str) -> str:
    """Regex 回退方案 — 比 HTMLParser 粗糙但永不报错."""
    # 移除整块标签
    for tag in _REMOVE_TAGS:
        html = re.sub(
            rf"<{tag}[^>]*>.*?</{tag}>", "",
            html, flags=re.DOTALL | re.IGNORECASE,
        )
    # 块级标签 → 换行
    html = re.sub(
        r"</?(?:" + "|".join(_BLOCK_TAGS) + r")[^>]*>",
        "\n", html, flags=re.IGNORECASE,
    )
    # 移除所有剩余标签
    html = re.sub(r"<[^>]+>", "", html)
    # 解码常见 HTML 实体
    entities = {
        "&amp;": "&", "&lt;": "<", "&gt;": ">", "&quot;": '"',
        "&apos;": "'", "&#39;": "'", "&nbsp;": " ",
        "&mdash;": "—", "&ndash;": "–", "&hellip;": "…",
    }
    for ent, ch in entities.items():
        html = html.replace(ent, ch)
    return html


# ── ZIM Reader ──────────────────────────────────────────

class ZimReader:
    """ZIM 文件读取器，自动选择后端.

    优先 libzim（mmap I/O，高性能），
    回退 zimply-core（纯 Python）。
    """

    def __init__(self, path: str | Path):
        self.path = Path(path)
        if not self.path.exists():
            raise FileNotFoundError(f"ZIM 文件不存在: {self.path}")
        self._backend = None
        self._backend_name = ""
        self._article_count = 0
        self._has_category_support = False

    # ── 生命周期 ────────────────────────────────────

    def open(self) -> None:
        """打开 ZIM 文件，自动选择后端."""
        if self._backend is not None:
            return

        # 尝试 libzim
        try:
            import libzim.reader
            self._backend = libzim.reader.Archive(str(self.path))
            self._backend_name = "libzim"
            self._article_count = self._backend.article_count
            # 检测 V namespace
            self._has_category_support = self._check_v_namespace_libzim()
            return
        except ImportError:
            pass
        except Exception as e:
            raise RuntimeError(f"libzim 打开 ZIM 文件失败: {e}") from e

        # 尝试 zimply-core
        try:
            import zimply_core
            raise ImportError("zimply-core 暂未实现，请安装 libzim")  # TODO
        except ImportError:
            pass

        raise ImportError(
            "需要安装 libzim 才能读取 ZIM 文件。\n"
            "  pip install libzim -i https://pypi.tuna.tsinghua.edu.cn/simple"
        )

    def close(self) -> None:
        """关闭 ZIM 文件."""
        self._backend = None
        self._backend_name = ""

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *args):
        self.close()

    # ── 属性 ────────────────────────────────────────

    @property
    def article_count(self) -> int:
        return self._article_count

    @property
    def has_category_support(self) -> bool:
        """V namespace 是否可用（支持按分类筛选）."""
        return self._has_category_support

    @property
    def backend_name(self) -> str:
        return self._backend_name

    # ── V namespace 检测 ───────────────────────────

    def _check_v_namespace_libzim(self) -> bool:
        """检测 libzim 后端的 V namespace 是否可用."""
        try:
            count = self._backend.all_entry_count
            # 抽样：开头、中间、结尾各 2000 条
            check_points = [
                (0, 2000),
                (count // 2, count // 2 + 2000),
                (max(0, count - 2000), count),
            ]
            for start, end in check_points:
                for i in range(start, min(end, count)):
                    try:
                        entry = self._backend._get_entry_by_id(i)
                        if entry.path.startswith("V/"):
                            return True
                    except Exception:
                        continue
        except Exception:
            pass
        return False

    # ── 标题发现（V namespace 不可用时的回退方案）───

    def discover_by_title(
        self, keywords: list[str],
        max_scan: int = 0,
        progress_callback=None,
    ) -> list[tuple[int, str]]:
        """扫描全部条目，返回标题含有关键词的文章 (entry_id, title) 列表.

        V namespace 不可用时使用此方法。

        Args:
            keywords: 中文关键词列表
            max_scan: 最多扫描条目数（0 = 全部）
            progress_callback: 可选，每 10 万条回调一次 (scanned, found)

        Returns:
            [(entry_id, title), ...] 列表
        """
        if not self._backend:
            raise RuntimeError("ZIM 文件未打开")

        results: list[tuple[int, str]] = []
        seen_titles: set[str] = set()

        count = self._backend.all_entry_count
        scan_limit = min(max_scan, count) if max_scan > 0 else count

        for i in range(scan_limit):
            try:
                entry = self._backend._get_entry_by_id(i)
            except Exception:
                continue

            # 只看 A namespace 非重定向文章
            if entry.path[0] != "A":
                continue
            if entry.is_redirect:
                continue

            title = entry.title
            if title in seen_titles:
                continue

            # 标题关键词匹配
            if any(kw in title for kw in keywords):
                results.append((i, title))
                seen_titles.add(title)

            # 进度回调
            if progress_callback and i % 100000 == 0 and i > 0:
                progress_callback(i, len(results))

        return results

    def iter_by_title_filter(
        self, keywords: list[str],
        max_articles: int = 0,
    ) -> Iterator[ZimArticle]:
        """流式迭代：扫描并产出标题含有关键词的文章.

        边扫描边产出，无需等待全部扫描完成。
        适合 max_articles 较小的场景。

        Args:
            keywords: 中文关键词列表
            max_articles: 最多返回文章数
        """
        if not self._backend:
            return

        yielded = 0
        seen_titles: set[str] = set()

        try:
            count = self._backend.all_entry_count
            for i in range(count):
                if max_articles > 0 and yielded >= max_articles:
                    break

                try:
                    entry = self._backend._get_entry_by_id(i)
                except Exception:
                    continue

                if entry.path[0] != "A":
                    continue
                if entry.is_redirect:
                    continue

                title = entry.title
                if title in seen_titles:
                    continue
                seen_titles.add(title)

                if not any(kw in title for kw in keywords):
                    continue

                try:
                    item = entry.get_item()
                    raw_html = bytes(item.content).decode("utf-8", errors="replace")
                except Exception:
                    continue

                text = _wiki_html_to_text(raw_html)

                yield ZimArticle(
                    title=title,
                    url=entry.path,
                    text=text,
                    namespace=entry.path[0],
                    mimetype=item.mimetype if hasattr(item, 'mimetype') else "text/html",
                    entry_id=i,
                )
                yielded += 1

        except Exception:
            pass

    # ── 分类发现 ────────────────────────────────────

    def discover_categories(
        self, keywords: list[str], max_scan: int = 100000
    ) -> list[CategoryInfo]:
        """扫描 V namespace，返回匹配关键词的分类列表.

        Args:
            keywords: 中文关键词列表，如 ["计算机", "编程", "AI"]
            max_scan: 最多扫描条目数（保护大文件不超时）

        Returns:
            匹配的 CategoryInfo 列表，按文章数降序
        """
        if not self._backend:
            raise RuntimeError("ZIM 文件未打开")

        if self._backend_name == "libzim":
            return self._discover_categories_libzim(keywords, max_scan)
        else:
            return []

    def _discover_categories_libzim(
        self, keywords: list[str], max_scan: int
    ) -> list[CategoryInfo]:
        """libzim 后端的分类发现."""
        categories: dict[str, CategoryInfo] = {}

        try:
            count = self._backend.all_entry_count
            scan_limit = min(max_scan, count)

            for i in range(scan_limit):
                try:
                    entry = self._backend._get_entry_by_id(i)
                    path = entry.path
                    # 只处理 V namespace 的 Category: 条目
                    if not path.startswith("V/Category:"):
                        continue

                    # 关键词匹配
                    if not any(kw in path for kw in keywords):
                        continue

                    # 读取二进制索引数组
                    item = entry.get_item()
                    raw = bytes(item.content)
                    n_articles = len(raw) // 4
                    if n_articles == 0:
                        continue

                    article_ids = list(
                        struct.unpack(f"<{n_articles}I", raw)
                    )

                    # 从路径提取分类名
                    name = path.replace("V/Category:", "").replace("V/", "")

                    categories[path] = CategoryInfo(
                        name=name,
                        path=path,
                        article_count=n_articles,
                        article_ids=article_ids,
                    )

                except Exception:
                    continue

        except Exception:
            pass

        # 按文章数降序排序
        return sorted(
            categories.values(),
            key=lambda c: c.article_count, reverse=True,
        )

    # ── 文章迭代 ────────────────────────────────────

    def iter_articles(
        self,
        namespaces: list[str] | None = None,
        max_articles: int = 0,
        skip_redirects: bool = True,
    ) -> Iterator[ZimArticle]:
        """迭代 ZIM 文章.

        Args:
            namespaces: 要迭代的 namespace 列表，默认 ["A"]
            max_articles: 最多返回文章数（0 = 不限）
            skip_redirects: 是否跳过重定向条目
        """
        if namespaces is None:
            namespaces = ["A"]

        if self._backend_name == "libzim":
            yield from self._iter_articles_libzim(
                namespaces, max_articles, skip_redirects,
            )

    def _iter_articles_libzim(
        self, namespaces: list[str],
        max_articles: int, skip_redirects: bool,
    ) -> Iterator[ZimArticle]:
        """libzim 后端的文章迭代."""
        yielded = 0
        ns_set = set(namespaces)

        try:
            count = self._backend.all_entry_count
            for i in range(count):
                if max_articles > 0 and yielded >= max_articles:
                    break

                try:
                    entry = self._backend._get_entry_by_id(i)
                except Exception:
                    continue

                # namespace 过滤
                if entry.path[0] not in ns_set:
                    continue

                # 跳过重定向
                if skip_redirects and entry.is_redirect:
                    continue

                # 提取内容
                try:
                    item = entry.get_item()
                    raw_html = bytes(item.content).decode("utf-8", errors="replace")
                except Exception:
                    continue

                text = _wiki_html_to_text(raw_html)

                article = ZimArticle(
                    title=entry.title,
                    url=entry.path,
                    text=text,
                    namespace=entry.path[0],
                    mimetype=item.mimetype if hasattr(item, 'mimetype') else "text/html",
                    entry_id=i,
                )
                yield article
                yielded += 1

        except Exception:
            pass

    # ── 按 ID 取文章 ──────────────────────────────

    def get_articles_by_ids(
        self, entry_ids: list[int],
        max_articles: int = 0,
    ) -> Iterator[ZimArticle]:
        """按条目 ID 列表批量取文章.

        Args:
            entry_ids: 条目 ID 列表（来自 V namespace 分类索引）
            max_articles: 最多返回数（0 = 不限）
        """
        if self._backend_name == "libzim":
            yield from self._get_articles_by_ids_libzim(entry_ids, max_articles)

    def _get_articles_by_ids_libzim(
        self, entry_ids: list[int], max_articles: int,
    ) -> Iterator[ZimArticle]:
        """libzim: 按 ID 取文章."""
        yielded = 0

        for eid in entry_ids:
            if max_articles > 0 and yielded >= max_articles:
                break

            try:
                entry = self._backend._get_entry_by_id(eid)
            except Exception:
                continue

            # 只取 A namespace（文章），跳过重定向
            if entry.path[0] != "A":
                continue
            if entry.is_redirect:
                continue

            try:
                item = entry.get_item()
                raw_html = bytes(item.content).decode("utf-8", errors="replace")
            except Exception:
                continue

            text = _wiki_html_to_text(raw_html)

            yield ZimArticle(
                title=entry.title,
                url=entry.path,
                text=text,
                namespace=entry.path[0],
                mimetype=item.mimetype if hasattr(item, 'mimetype') else "text/html",
                entry_id=eid,
            )
            yielded += 1

    # ── 元数据 ──────────────────────────────────────

    def get_metadata(self, key: str) -> Optional[str]:
        """读取 ZIM 元数据条目."""
        if self._backend_name == "libzim":
            try:
                entry = self._backend.get_entry_by_path(f"M/{key}")
                item = entry.get_item()
                return bytes(item.content).decode("utf-8", errors="replace")
            except Exception:
                pass

            # 尝试 libzim 内置 metadata API
            try:
                return self._backend.get_metadata(key)
            except Exception:
                pass

        return None

    def print_info(self) -> None:
        """打印 ZIM 文件基本信息."""
        print(f"ZIM 文件: {self.path}")
        print(f"后端: {self._backend_name}")
        print(f"文章数: {self._article_count:,}")
        print(f"分类支持: {'是' if self._has_category_support else '否'}")

        title = self.get_metadata("Title")
        lang = self.get_metadata("Language")
        desc = self.get_metadata("Description")
        if title:
            print(f"标题: {title}")
        if lang:
            print(f"语言: {lang}")
        if desc:
            print(f"描述: {desc[:120]}")
