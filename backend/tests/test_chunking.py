"""Markdown 切块器（Task 7）：标题分段 / 页标记剥离 / 句级打包与重叠 / 硬切 / 表格原子 / 索引连续。

测试输入按计划钉死的算法构造：
- 「三段各 300 字」段内不带句读 → 缓冲 300→600→900 才超 target，恰 flush 一次
- 「两段各 400 字」段内每 100 字一句 → 缓冲中途超 target，产生携带重叠的第二 chunk
"""
from app.services.chunking import ChunkDraft, chunk_markdown, estimate_tokens


def test_headings_split():
    md = "# A\n" + "字" * 100 + "\n## B\n" + "字" * 100
    chunks = chunk_markdown(md, target=600)
    assert len(chunks) == 2
    assert chunks[1].content.split("\n", 1)[0] == "## B"


def test_page_markers_extracted():
    md = "<!-- page:3 -->\n" + "字" * 50 + "。"
    chunks = chunk_markdown(md)
    assert len(chunks) == 1
    assert chunks[0].page_number == 3
    assert "<!--" not in chunks[0].content


def test_long_paragraph_hard_split():
    md = "字" * 1500
    chunks = chunk_markdown(md, target=600, overlap=60)
    assert len(chunks) >= 3
    assert all(len(c.content) <= 1200 for c in chunks)
    assert chunks[1].content[:60] == chunks[0].content.rstrip()[-60:]


def test_table_rows_not_split():
    rows = ["|字" * 10 for _ in range(35)]  # 每行 20 字符 × 35 行 = 700+ 字符表格
    md = "表格如下\n" + "\n".join(rows)
    chunks = chunk_markdown(md, target=600)
    table_lines = [ln for c in chunks for ln in c.content.split("\n") if ln.startswith("|")]
    assert len(table_lines) == 35
    assert set(table_lines) == set(rows)  # 每行完整，无跨 chunk 拆断


def test_overlap_carry():
    # 三段各 300 字（段内无句读）→ 1 chunk，无重叠可言
    md3 = "\n\n".join("字" * 299 + "。" for _ in range(3))
    assert len(chunk_markdown(md3, target=600)) == 1

    # 两段各 400 字（段内每 100 字一句）→ 2 chunks，第二 chunk 以第一 chunk 末 60 字开头
    def para400() -> str:
        return "".join("字" * 99 + "。" for _ in range(4))

    chunks = chunk_markdown(para400() + "\n\n" + para400(), target=600, overlap=60)
    assert len(chunks) == 2
    assert chunks[1].content.startswith(chunks[0].content[-60:])


def test_index_continuous():
    assert chunk_markdown("") == []
    md = "# T\n" + "字" * 1300 + "\n<!-- page:2 -->\n## S\n" + "字" * 50 + "\n" + "|a" * 10 + "\n尾文本"
    chunks = chunk_markdown(md, target=600)
    assert len(chunks) >= 3  # 混合输入确实产出多个 chunk，索引断言非平凡
    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))


def test_estimate_tokens():
    assert estimate_tokens("中文abc") == 5
    assert estimate_tokens("") == 0
