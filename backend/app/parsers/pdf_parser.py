"""pdf → Markdown 解析器（Plan 1 Task 6）：逐页文本 + 页标记；无文本层判扫描件。

Review Focus #1 的解析半边：扫描件（全文 < 20 字符）必须 ok=False，
绝不允许产出 0 内容却「已完成」——OCR 属二期。
"""
import pymupdf

from app.parsers.base import ParseResult

_MIN_TEXT_CHARS = 20  # 全文低于此阈值视为无文本层（扫描件）


class PdfParser:
    """Parser 的 pdf 实现；任何异常折叠为 ok=False + 中文 reason。"""

    def parse(self, data: bytes, filename: str) -> ParseResult:
        try:
            return self._parse(data, filename)
        except Exception as e:  # noqa: BLE001 管线要求失败原因而非异常栈
            return ParseResult(ok=False, reason=f"pdf 解析失败：{e}（文件：{filename}）")

    def _parse(self, data: bytes, filename: str) -> ParseResult:
        with pymupdf.open(stream=data, filetype="pdf") as doc:
            page_texts = [page.get_text("text").strip() for page in doc]
        if sum(len(t) for t in page_texts) < _MIN_TEXT_CHARS:
            return ParseResult(
                ok=False,
                reason="疑似扫描件：未提取到文本层，请上传文字版或等待 OCR 支持",
            )
        blocks = [f"<!-- page:{i} -->\n\n{text}" for i, text in enumerate(page_texts, start=1)]
        return ParseResult(ok=True, markdown="\n\n".join(blocks))
