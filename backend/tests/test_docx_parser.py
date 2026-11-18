"""docx 解析器（Task 5）：测试内用 python-docx 现场构建 docx，断言 md 映射规则。

红线 3：不触网——构建与解析全在内存。
"""
import io

import pytest
from docx import Document as build_docx

from app.parsers import SUPPORTED_FILE_TYPES, get_parser


def _make_docx() -> bytes:
    """构建计划 Step 1 指定的文档：Heading 1 + 正文两段 + List Bullet + 2 行 3 列表格。"""
    doc = build_docx()
    doc.add_heading("产品介绍", level=1)
    doc.add_paragraph("这是第一段正文。")
    doc.add_paragraph("这是第二段正文。")
    doc.add_paragraph("要点一条", style="List Bullet")
    table = doc.add_table(rows=2, cols=3)
    for r, row in enumerate(table.rows):
        for c, cell in enumerate(row.cells):
            cell.text = f"格{r}{c}"
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def test_docx_to_markdown_mapping():
    result = get_parser("docx").parse(_make_docx(), "产品手册.docx")
    assert result.ok is True
    md = result.markdown
    assert "# 产品介绍" in md  # Heading 1 → #×1
    assert "- 要点一条" in md  # List → 「- 」前缀
    assert "这是第一段正文。" in md  # 正文保留
    assert "这是第二段正文。" in md
    table_lines = [ln for ln in md.splitlines() if ln.startswith("|")]
    assert len(table_lines) == 3  # 表头 + 分隔行 + 数据行（2 行表）
    assert set(table_lines[1]) <= set("|-")  # 第二行是 |---|---| 分隔行


def test_registry_dispatch_and_whitelist():
    assert SUPPORTED_FILE_TYPES == {"docx", "pdf", "xlsx", "txt", "md", "csv", "html"}
    assert get_parser("docx") is not None
    with pytest.raises(ValueError):
        get_parser("exe")


def test_garbage_bytes_fail_gracefully():
    """坏字节 → ok=False + 中文 reason（将写入 document.status_reason）。"""
    result = get_parser("docx").parse(b"this is not a docx", "fake.docx")
    assert result.ok is False
    assert result.reason
