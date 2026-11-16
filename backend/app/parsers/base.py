"""解析器公共契约（Plan 1 Task 5/6）：ParseResult / Parser Protocol / ParseError。"""
from dataclasses import dataclass
from typing import Protocol


@dataclass
class ParseResult:
    """解析结果：ok=False 时 reason 为中文失败原因（管线写入 document.status_reason）。"""

    ok: bool
    markdown: str = ""
    reason: str | None = None


class Parser(Protocol):
    """单文件解析器接口：字节流 + 原始文件名 → ParseResult（不触网、不落库）。"""

    def parse(self, data: bytes, filename: str) -> ParseResult: ...


class ParseError(Exception):
    """解析失败异常（webpage 等抛异常式接口用；管线捕获后折叠进 ParseResult）。"""

