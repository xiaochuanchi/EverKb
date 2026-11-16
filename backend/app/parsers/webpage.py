"""网页抓取 + 正文抽取（Plan 1 Task 6）：trafilatura 主体识别，导航/页脚噪音剔除。

fetch_and_extract 为薄壳（httpx 拉取 → html_to_markdown），网络行为不单测，
真实连通性由管线 e2e（Task 15）覆盖。
"""
import httpx
import trafilatura
from lxml import etree

from app.parsers.base import ParseError

_UA = "everkb/0.1"

# 结构噪音标签：抽取前机械剔除（trafilatura 对内容极少的小页面的启发式会漏掉 nav，
# 大页面它自己也能剔除，这里双保险，确定性更高）
_NOISE_XPATH = "//nav | //header | //footer | //aside | //script | //style | //noscript"


def html_to_markdown(html: bytes) -> str:
    """正文 → Markdown（trafilatura output_format=markdown）；无正文抛 ParseError。"""
    # 先按 utf-8 显式解码再进 lxml：bytes 直传时 HTMLParser 会做 charset 猜测，
    # 无 <meta charset> 的页面会被误判为 latin-1（非 UTF-8 页面属已知局限，Task 15 e2e 复评）
    text = html.decode("utf-8", errors="replace")
    tree = etree.fromstring(text, parser=etree.HTMLParser())
    for bad in tree.xpath(_NOISE_XPATH):
        bad.getparent().remove(bad)
    cleaned = etree.tostring(tree, method="html", encoding="unicode")
    md = trafilatura.extract(cleaned, output_format="markdown", include_tables=True)
    if not md:
        raise ParseError("网页正文提取失败：未识别到正文内容")
    return md


def fetch_and_extract(url: str, timeout: float = 30.0) -> tuple[bytes, str]:
    """拉取网页 → (原始 html bytes, 正文 md)；HTTP 错误抛 httpx 异常（管线折叠为 status_reason）。

    follow_redirects=True：目标页常 301/302 跳转（短链、http→https），不跟随即失败。
    """
    with httpx.Client(headers={"User-Agent": _UA}, timeout=timeout, follow_redirects=True) as client:
        resp = client.get(url)
        resp.raise_for_status()
        html = resp.content
    return html, html_to_markdown(html)
