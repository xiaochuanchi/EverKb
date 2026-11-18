"""本地 html 文件 → Markdown 解析器：复用网页抓取的 html_to_markdown 抽取逻辑。"""

from app.parsers.base import ParseResult
from app.parsers.webpage import html_to_markdown


class HtmlParser:
    """Parser 的 html 实现；抽取失败折叠为 ok=False + 中文 reason。"""

    def parse(self, data: bytes, filename: str) -> ParseResult:
        try:
            return ParseResult(ok=True, markdown=html_to_markdown(data))
        except Exception as e:  # noqa: BLE001 管线要求失败原因而非异常栈
            return ParseResult(ok=False, reason=f"html 解析失败：{e}（文件：{filename}）")
