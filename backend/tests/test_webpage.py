"""网页解析（Task 6）：html_to_markdown 主体抽取（fetch_and_extract 为薄壳不出网，不单测）。"""
import pytest

from app.parsers import ParseError
from app.parsers.webpage import html_to_markdown

_HTML = """<html><head><title>t</title></head><body>
<nav><a href="/">首页</a><a href="/about">导航文案不应出现</a></nav>
<article><h1>EverKB 解析器</h1>
<p>正文关键词：可插拔存储与自研 trace 埋点。</p></article>
<footer>页脚噪音</footer>
</body></html>""".encode("utf-8")


def test_html_extracts_main_content_drops_chrome():
    md = html_to_markdown(_HTML)
    assert "正文关键词" in md  # article 正文保留
    assert "导航文案不应出现" not in md  # nav 噪音剔除


def test_empty_body_raises_parse_error():
    with pytest.raises(ParseError):
        html_to_markdown(b"<html><body></body></html>")
