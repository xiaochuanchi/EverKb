"""xlsx 解析器（Task 6）：openpyxl 现场造表，断言管道表拆分与工作表标题。"""
import io

from openpyxl import Workbook

from app.parsers import get_parser


def _make_xlsx() -> bytes:
    """表头 3 列 + 25 行数据（计划 Step 2：> 20 拆两张 20+5）。"""
    wb = Workbook()
    ws = wb.active
    ws.title = "Sheet"
    ws.append(["名称", "数量", "单价"])
    for i in range(1, 26):
        ws.append([f"物品{i}", i, round(i * 1.5, 2)])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _pipe_lines(md: str) -> list[str]:
    return [ln for ln in md.splitlines() if ln.startswith("|")]


def test_xlsx_chunks_over_20_data_rows():
    result = get_parser("xlsx").parse(_make_xlsx(), "清单.xlsx")
    assert result.ok is True
    md = result.markdown
    assert "# 工作表: Sheet" in md  # sheet 首块前的标题
    pipes = _pipe_lines(md)
    assert len(pipes) == (2 + 20) + (2 + 5)  # 两张表：表头+分隔+数据 20；表头+分隔+数据 5
    sep_count = sum(1 for ln in pipes if set(ln) <= set("|-"))
    assert sep_count == 2  # 两张表各一条分隔行
    assert "物品1" in md and "物品25" in md  # 首尾数据都在


def test_xlsx_multi_sheet_titles():
    wb = Workbook()
    ws1 = wb.active
    ws1.title = "总览"
    ws1.append(["列A"])
    ws1.append(["值1"])
    ws2 = wb.create_sheet("明细")
    ws2.append(["列B"])
    ws2.append(["值2"])
    buf = io.BytesIO()
    wb.save(buf)
    result = get_parser("xlsx").parse(buf.getvalue(), "多表.xlsx")
    assert result.ok is True
    assert "# 工作表: 总览" in result.markdown
    assert "# 工作表: 明细" in result.markdown
