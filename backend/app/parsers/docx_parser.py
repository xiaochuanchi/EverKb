"""docx → Markdown 解析器（Plan 1 Task 5）。

映射规则（计划 Step 3）：
- style 名以 Heading/标题 开头 → 取级别 N，输出 #×N + 空格 + 文本
  （前缀匹配不区分大小写：真实中文 Word 文档的内置样式名可能存为小写 "heading 1"）
- style 名以 List 开头 → 「- 」前缀
- 普通段落原样；空段落跳过
- 表格逐行转 | a | b | 管道表，首行后插 |---| 分隔行
"""
import io

from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph

from app.parsers.base import ParseResult

_W_P, _W_TBL = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p", "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}tbl"


class DocxParser:
    """Parser 的 docx 实现；任何异常折叠为 ok=False + 中文 reason，绝不向上抛。"""

    def parse(self, data: bytes, filename: str) -> ParseResult:
        try:
            return self._parse(data, filename)
        except Exception as e:  # noqa: BLE001 管线要求失败原因而非异常栈
            return ParseResult(ok=False, reason=f"docx 解析失败：{e}（文件：{filename}）")

    def _parse(self, data: bytes, filename: str) -> ParseResult:
        doc = Document(io.BytesIO(data))
        lines: list[str] = []
        for child in doc.element.body.iterchildren():
            if child.tag == _W_P:
                text, style = self._para_text(Paragraph(child, doc))
                if not text:
                    continue  # 空段落跳过
                lines.append(self._render_paragraph(text, style))
            elif child.tag == _W_TBL:
                lines.append(self._render_table(Table(child, doc)))
        return ParseResult(ok=True, markdown="\n".join(lines))

    @staticmethod
    def _para_text(para: Paragraph) -> tuple[str, str]:
        return para.text.strip(), para.style.name if para.style is not None else ""

    @staticmethod
    def _heading_level(style_name: str) -> int | None:
        name = style_name.lower()
        if not (name.startswith("heading") or style_name.startswith("标题")):
            return None
        for token in style_name.replace("标题", " ").split():
            if token.isdigit():
                return int(token)
        return None  # 有 Heading 前缀但无级别 → 当普通段落

    @classmethod
    def _render_paragraph(cls, text: str, style_name: str) -> str:
        level = cls._heading_level(style_name)
        if level:
            return f"{'#' * level} {text}"
        if style_name.startswith("List"):
            return f"- {text}"
        return text

    @staticmethod
    def _render_table(table: Table) -> str:
        rows = ["| " + " | ".join(cell.text.strip() for cell in row.cells) + " |" for row in table.rows]
        separator = "|" + "|".join(["---"] * len(table.columns)) + "|"
        return "\n".join([rows[0], separator, *rows[1:]])
