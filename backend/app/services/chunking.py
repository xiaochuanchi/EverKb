"""Markdown 切块器（Plan 1 Task 7）。

算法（计划钉死，唯一允许的实现分歧点）：
- 逐行扫描：`<!-- page:N -->` 更新当前页码并丢弃；`#`~`######` 标题行开新段；
  连续 `|` 开头行为表格块（原子，绝不跨 chunk 拆断）；空行丢弃
- 段内按句边界 ``(?<=[。！？!?；;\n])`` 切句打包：缓冲超 target 且非空则 flush 为
  chunk，段内下一 chunk 以被 flush 内容末尾 overlap 字符开头
- 单句超 target×2 硬切：片长 target、片间重叠 overlap，各片独立成 chunk
- chunk.content 首行为所属最近标题行（若正文首行不是该标题）；
  page_number 取开段前最近的 page 标记

参数约束：target > 0 且 0 <= overlap < target，越界抛 ValueError（Task 10 接配置前挡住退化值）。
"""
import re
from dataclasses import dataclass

_PAGE_RE = re.compile(r"^<!--\s*page:(\d+)\s*-->$")
_HEADING_RE = re.compile(r"^#{1,6}\s")
_SENTENCE_RE = re.compile(r"(?<=[。！？!?；;\n])")


@dataclass
class ChunkDraft:
    content: str
    chunk_index: int            # 0 起连续
    page_number: int | None     # 来自最近一个 page 标记


def estimate_tokens(text: str) -> int:
    """中文近似：1 字符 ≈ 1 token；预留换 tokenizer。"""
    return len(text)


class _Section:
    """一个标题段：标题行 + 按序排列的文本行/表格块 + 开段时页码。"""

    def __init__(self, heading: str | None, page_number: int | None) -> None:
        self.heading = heading
        self.page_number = page_number
        self.items: list[tuple[str, str]] = []  # ("text", 行) | ("table", 多行块)


def _scan_sections(md: str) -> list[_Section]:
    sections: list[_Section] = []
    current: _Section | None = None
    page: int | None = None
    table_buf: list[str] = []

    def open_section(heading: str | None) -> _Section:
        nonlocal current
        current = _Section(heading, page)
        sections.append(current)
        return current

    def close_table() -> None:
        # 表格块在首个非 | 行（含空行/标记/标题）处收口，整块原子进出
        nonlocal table_buf
        if table_buf:
            current.items.append(("table", "\n".join(table_buf)))  # type: ignore[union-attr]
        table_buf = []

    for raw in md.splitlines():
        line = raw.strip()
        if line.startswith("|"):
            if current is None:
                open_section(None)
            table_buf.append(line)
            continue
        close_table()
        if not line:
            continue  # 空行丢弃
        m = _PAGE_RE.match(line)
        if m:
            page = int(m.group(1))  # 更新页码，标记行丢弃
            continue
        if _HEADING_RE.match(line):
            open_section(line)  # 标题行开新段，标题本身不进正文
            continue
        if current is None:
            open_section(None)  # 首个正文前无标题 → 匿名段
        current.items.append(("text", line))  # type: ignore[union-attr]
    close_table()
    return sections


def _pack_section(
    section: _Section,
    target: int,
    overlap: int,
    chunks: list[str],
    pages: list[int | None],
) -> None:
    def emit(text: str) -> None:
        first_line = text.split("\n", 1)[0]
        if section.heading and first_line != section.heading:
            text = f"{section.heading}\n{text}"  # chunk 首行为所属最近标题行
        chunks.append(text)
        pages.append(section.page_number)

    # 段内打包单元：连续文本行合并后切句（句内保留行尾换行）；表格块整块原子进出
    units: list[tuple[bool, str]] = []  # (是否表格, 内容)
    text_run: list[str] = []
    for kind, payload in section.items:
        if kind == "text":
            text_run.append(payload)
            continue
        if text_run:
            units.extend((False, s) for s in _SENTENCE_RE.split("\n".join(text_run)) if s.strip())
            text_run = []
        units.append((True, payload))
    if text_run:
        units.extend((False, s) for s in _SENTENCE_RE.split("\n".join(text_run)) if s.strip())

    carry = ""    # 上一 flush 的末尾 overlap 字符，段内下一 chunk 以它开头
    pending = ""  # 当前在途累积（已含 carry）
    after_block = False  # 上一个单元是表格块 → 下一个单元前补换行，避免粘连
    step = max(target - overlap, 1)
    for is_table, unit in units:
        if not is_table and len(unit) > target * 2:
            if pending and pending != carry:
                emit(pending)  # 硬切前先收掉在途缓冲（仅剩 carry 则丢弃）
            last = ""
            for pos in range(0, len(unit), step):
                piece = unit[pos:pos + target]
                emit(piece)  # 硬切片各自成 chunk，片间自带 overlap 重叠
                last = piece
            carry = last.rstrip()[-overlap:] if overlap > 0 else ""  # 防 s[-0:] 取整串
            pending = carry
            after_block = False
            continue
        if pending and (is_table or after_block):
            pending += "\n"  # 表格块与相邻单元保持独立行
        pending += unit
        after_block = is_table
        if len(pending) > target:  # 缓冲超 target 且非空 → flush
            emit(pending)
            # 表尾不携带（表行跨 chunk 重复违背表格验收口径）；overlap=0 时防 s[-0:] 取整串
            carry = "" if after_block or overlap <= 0 else pending.rstrip()[-overlap:]
            pending = carry
    if pending and pending != carry:  # 段尾收口：仅剩 carry 时不成 chunk
        emit(pending)


def chunk_markdown(md: str, target: int = 600, overlap: int = 60) -> list[ChunkDraft]:
    if target <= 0 or not (0 <= overlap < target):
        raise ValueError(f"非法切块参数：target={target}, overlap={overlap}（要求 target>0 且 0<=overlap<target）")
    chunks: list[str] = []
    pages: list[int | None] = []
    for section in _scan_sections(md):
        _pack_section(section, target, overlap, chunks, pages)
    return [
        ChunkDraft(content=content, chunk_index=index, page_number=page)
        for index, (content, page) in enumerate(zip(chunks, pages))
    ]
