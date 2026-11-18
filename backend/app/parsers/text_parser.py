"""txt / md 纯文本 → Markdown 解析器（均透传，不触网、不落库）。

- txt：按 utf-8 解码，失败退 latin-1，再失败报错；去除行尾空白、跳过连续空行。
- md：本身即 Markdown，原样透传。
"""

from app.parsers.base import ParseResult

_ENCODINGS = ("utf-8", "gb18030", "latin-1")


class TextParser:
    """Parser 的 txt 实现；任何异常折叠为 ok=False + 中文 reason。"""

    def parse(self, data: bytes, filename: str) -> ParseResult:
        try:
            return self._parse(data, filename)
        except Exception as e:  # noqa: BLE001 管线要求失败原因而非异常栈
            return ParseResult(ok=False, reason=f"txt 解析失败：{e}（文件：{filename}）")

    def _parse(self, data: bytes, filename: str) -> ParseResult:
        text = self._decode(data)
        lines = [line.rstrip() for line in text.splitlines()]
        return ParseResult(ok=True, markdown="\n".join(lines))

    @staticmethod
    def _decode(data: bytes) -> str:
        for enc in _ENCODINGS:
            try:
                return data.decode(enc)
            except UnicodeDecodeError:
                continue
        return data.decode("utf-8", errors="replace")  # 兜底：宁可不乱码也不抛


class MarkdownParser:
    """Parser 的 md 实现：原样透传（md 即目标格式）。"""

    def parse(self, data: bytes, filename: str) -> ParseResult:
        try:
            return ParseResult(ok=True, markdown=self._decode(data))
        except Exception as e:  # noqa: BLE001
            return ParseResult(ok=False, reason=f"md 解析失败：{e}（文件：{filename}）")

    @staticmethod
    def _decode(data: bytes) -> str:
        for enc in _ENCODINGS:
            try:
                return data.decode(enc)
            except UnicodeDecodeError:
                continue
        return data.decode("utf-8", errors="replace")
