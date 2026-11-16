"""pdf 解析器（Task 6）：pymupdf 现场造 PDF（含文本页 / 无文本扫描件两类）。"""
import pymupdf

from app.parsers import get_parser


def _make_pdf(pages: list[str]) -> bytes:
    doc = pymupdf.open()
    for text in pages:
        page = doc.new_page()
        if text:
            # 默认 helv 字体无 CJK 字形（写入即空壳）→ 必须用内置简体中文字体
            page.insert_text((72, 72), text, fontsize=12, fontname="china-s")
    buf = doc.tobytes()
    doc.close()
    return buf


def test_pdf_pages_with_markers():
    p1 = "第一页：产品介绍与核心功能概述，面向知识库管理平台的入门用户。"
    p2 = "第二页：安装步骤与环境要求，包含 Docker Compose 一键起依赖的完整说明。"
    result = get_parser("pdf").parse(_make_pdf([p1, p2]), "手册.pdf")
    assert result.ok is True
    md = result.markdown
    assert "<!-- page:1 -->" in md
    assert "<!-- page:2 -->" in md
    assert p1 in md
    assert p2 in md


def test_pdf_without_text_layer_is_scanned():
    """无文本层（<20 字符）→ ok=False，reason 含「扫描件」（Review Focus #1 的解析半边）。"""
    result = get_parser("pdf").parse(_make_pdf([""]), "扫描件.pdf")
    assert result.ok is False
    assert "扫描件" in result.reason
