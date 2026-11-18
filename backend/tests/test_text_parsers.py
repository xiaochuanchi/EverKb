"""txt / md / csv / html 解析器：内存内构造，断言透传与转表逻辑（红线 3：不触网）。"""
import pytest

from app.parsers import get_parser


def test_txt_transparent():
    data = "第一行\n第二行\n\n第三行  ".encode("utf-8")
    result = get_parser("txt").parse(data, "笔记.txt")
    assert result.ok is True
    assert "第一行" in result.markdown
    assert "第三行" in result.markdown


def test_md_transparent():
    data = "# 标题\n\n正文内容\n- 列表项".encode("utf-8")
    result = get_parser("md").parse(data, "文档.md")
    assert result.ok is True
    assert result.markdown == "# 标题\n\n正文内容\n- 列表项"


def test_csv_to_pipe_table():
    data = "名称,数量\n物品1,1\n物品2,2".encode("utf-8")
    result = get_parser("csv").parse(data, "清单.csv")
    assert result.ok is True
    md = result.markdown
    assert "| 名称 | 数量 |" in md
    assert "| 物品1 | 1 |" in md
    assert "| 物品2 | 2 |" in md
    assert set(md.splitlines()[1]) <= set("|-")  # 分隔行


def test_html_extracts_body():
    html = b"<html><body><h1>\xe6\xa0\x87\xe9\xa2\x98</h1><p>\xe6\xad\xa3\xe6\x96\x87\xe5\x86\x85\xe5\xae\xb9</p></body></html>"
    result = get_parser("html").parse(html, "页面.html")
    assert result.ok is True
    assert "正文内容" in result.markdown


def test_registry_dispatch_new_types():
    for ft in ("txt", "md", "csv", "html"):
        assert get_parser(ft) is not None
    with pytest.raises(ValueError):
        get_parser("exe")
