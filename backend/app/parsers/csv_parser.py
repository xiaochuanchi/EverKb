"""csv → Markdown 解析器：转管道表，复用 xlsx 的拆表约定（数据行 > 20 拆表）。"""

import csv
import io

from app.parsers.base import ParseResult

_DATA_ROWS_PER_TABLE = 20  # 与 xlsx_parser 保持一致


class CsvParser:
    """Parser 的 csv 实现；任何异常折叠为 ok=False + 中文 reason。"""

    def parse(self, data: bytes, filename: str) -> ParseResult:
        try:
            return self._parse(data, filename)
        except Exception as e:  # noqa: BLE001 管线要求失败原因而非异常栈
            return ParseResult(ok=False, reason=f"csv 解析失败：{e}（文件：{filename}）")

    def _parse(self, data: bytes, filename: str) -> ParseResult:
        text = self._decode(data)
        rows = list(csv.reader(io.StringIO(text)))
        rows = [[c.strip() for c in row] for row in rows if any(c.strip() for c in row)]
        if not rows:
            return ParseResult(ok=True, markdown="")  # 空文件不报错，产出空 md
        header, data_rows = rows[0], rows[1:]
        blocks: list[str] = []
        for start in range(0, len(data_rows), _DATA_ROWS_PER_TABLE):
            chunk = [header] + data_rows[start : start + _DATA_ROWS_PER_TABLE]
            blocks.append(self._to_pipe_table(chunk))
        return ParseResult(ok=True, markdown="\n\n".join(blocks))

    @staticmethod
    def _decode(data: bytes) -> str:
        for enc in ("utf-8", "gb18030", "latin-1"):
            try:
                return data.decode(enc)
            except UnicodeDecodeError:
                continue
        return data.decode("utf-8", errors="replace")

    @staticmethod
    def _to_pipe_table(rows: list[list[str]]) -> str:
        lines = ["| " + " | ".join(row) + " |" for row in rows]
        separator = "|" + "|".join(["---"] * len(rows[0])) + "|"
        return "\n".join([lines[0], separator, *lines[1:]])
