"""xlsx → Markdown 解析器（Plan 1 Task 6）：每 sheet 转管道表，数据行 > 20 拆表。"""
import io

from openpyxl import load_workbook

from app.parsers.base import ParseResult

_DATA_ROWS_PER_TABLE = 20  # 每张管道表的数据行上限（表头每张都带，保持分块可读）


class XlsxParser:
    """Parser 的 xlsx 实现；任何异常折叠为 ok=False + 中文 reason。"""

    def parse(self, data: bytes, filename: str) -> ParseResult:
        try:
            return self._parse(data, filename)
        except Exception as e:  # noqa: BLE001 管线要求失败原因而非异常栈
            return ParseResult(ok=False, reason=f"xlsx 解析失败：{e}（文件：{filename}）")

    def _parse(self, data: bytes, filename: str) -> ParseResult:
        wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        blocks: list[str] = []
        for ws in wb.worksheets:
            rows_iter = ws.iter_rows(values_only=True)
            header = next(rows_iter, None)
            if header is None:
                continue  # 空 sheet 跳过
            data_rows = [
                [self._cell(v) for v in row]
                for row in rows_iter
                if any(v is not None and str(v).strip() for v in row)
            ]
            sheet_blocks = [f"# 工作表: {ws.title}"]
            for start in range(0, len(data_rows), _DATA_ROWS_PER_TABLE):
                chunk = [header] + data_rows[start : start + _DATA_ROWS_PER_TABLE]
                sheet_blocks.append(self._to_pipe_table(chunk))
            blocks.append("\n\n".join(sheet_blocks))
        wb.close()
        return ParseResult(ok=True, markdown="\n\n".join(blocks))

    @staticmethod
    def _cell(value) -> str:
        return "" if value is None else str(value).strip()

    @staticmethod
    def _to_pipe_table(rows: list[list[str]]) -> str:
        lines = ["| " + " | ".join(row) + " |" for row in rows]
        separator = "|" + "|".join(["---"] * len(rows[0])) + "|"
        return "\n".join([lines[0], separator, *lines[1:]])
