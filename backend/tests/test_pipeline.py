"""处理管线（Task 10）：状态机推进、幂等清残留、替换语义、失败折叠。

红线 3：不触网——FakeEmbedder/FakeVector/LocalDiskStorage 全程内存与临时目录。
"""
import pytest
from pymupdf import open as pdf_open

from app.models import Chunk, DocumentStatus, SourceType
from app.services.pipeline import content_key_for, process_document, run_pending
from tests.conftest import make_docx_bytes


def _make_pdf(pages: list[str]) -> bytes:
    doc = pdf_open()
    for text in pages:
        page = doc.new_page()
        if text:
            page.insert_text((72, 72), text, fontsize=12, fontname="china-s")
    buf = doc.tobytes()
    doc.close()
    return buf


def _chunk_rows(env, doc_id):
    return (
        env.session.query(Chunk)
        .filter(Chunk.document_id == doc_id)
        .order_by(Chunk.chunk_index)
        .all()
    )


def test_happy_path_docx(pipeline_env, make_document, seed_source, process_doc):
    """全链路走完：status==6、content.md 落存储、chunk 全部 vectorized、向量 enabled 随 doc。"""
    doc = make_document(enabled=False)  # enabled=False 使「row.enabled==doc.enabled」断言非平凡
    seed_source(doc, make_docx_bytes([
        ("产品介绍", ["这是第一段正文，介绍平台的核心能力。"]),
        ("安装步骤", ["使用 Docker Compose 一键启动全部依赖服务。"]),
    ]))

    process_doc(doc.id)

    assert doc.status == DocumentStatus.COMPLETED
    md = pipeline_env.storage.get_bytes(content_key_for(doc.oss_key))
    assert "产品介绍".encode() in md  # content.md 已生成于存储层
    rows = _chunk_rows(pipeline_env, doc.id)
    assert len(rows) == 2  # 两个标题段 → 2 chunk
    assert all(r.vectorized is True for r in rows)
    assert pipeline_env.vector.count_by_doc(doc.id) == len(rows)
    assert all(pipeline_env.vector._rows[r.id].enabled == doc.enabled for r in rows)
    assert doc.chunk_count == len(rows)
    assert doc.status_reason is None


def test_scanned_pdf_fails(pipeline_env, make_document, seed_source, process_doc):
    """无文本层 PDF：status==7、reason 含「扫描件」、0 chunk（Review Focus #1）。"""
    doc = make_document(file_type="pdf")
    seed_source(doc, _make_pdf([""]))

    process_doc(doc.id)

    assert doc.status == DocumentStatus.FAILED
    assert "扫描件" in (doc.status_reason or "")
    assert _chunk_rows(pipeline_env, doc.id) == []


def test_retry_cleans_leftover_chunks(pipeline_env, make_document, seed_source, process_doc):
    """半途崩溃重试（红线 4）：进入 status==4 → 先清残留 chunk 行与向量再从头执行。"""
    from app.services.vector import VectorRow

    doc = make_document()
    seed_source(doc, make_docx_bytes([("标题", ["重试后应全新入库的正文内容。"])]))
    doc.status = DocumentStatus.CHUNKED  # 预置：崩溃于切块之后
    # 显式高位 id：MySQL 自增不复用已删 id，SQLite 无 AUTOINCREMENT 会复用——
    # 用显式 id 模拟 MySQL 真实语义（旧行删除后新行必得全新 id）
    leftovers = [
        Chunk(id=101, document_id=doc.id, kb_id=doc.kb_id, chunk_index=0,
              page_number=None, content="残留块一", token_count=4, vectorized=True),
        Chunk(id=102, document_id=doc.id, kb_id=doc.kb_id, chunk_index=1,
              page_number=None, content="残留块二", token_count=4, vectorized=True),
    ]
    pipeline_env.session.add_all(leftovers)
    pipeline_env.session.commit()
    old_ids = [c.id for c in leftovers]
    # 预置 Milvus 残留向量（模拟上次向量化到一半崩溃）
    pipeline_env.vector.insert([
        VectorRow(id=oid, vector=[1.0] * 8, chunk_text="残留", page_number=None,
                  doc_id=doc.id, kb_id=doc.kb_id, enabled=True)
        for oid in old_ids
    ])

    process_doc(doc.id)

    rows = _chunk_rows(pipeline_env, doc.id)
    assert {r.id for r in rows}.isdisjoint(old_ids)  # MySQL 全新 ids
    assert doc.status == DocumentStatus.COMPLETED
    assert pipeline_env.vector.count_by_doc(doc.id) == len(rows)
    assert all(oid not in pipeline_env.vector._rows for oid in old_ids)  # 旧向量已清


def test_replace_clears_old_chunk_ids(pipeline_env, make_document, seed_source, process_doc):
    """替换重传（红线 2）：status=1/version=2 进入 → 旧版本不断供，成功后按 ids 精准清旧。"""
    doc = make_document()
    seed_source(doc, make_docx_bytes([
        ("第一章", ["初版内容一。"]), ("第二章", ["初版内容二。"]),
    ]))
    process_doc(doc.id)
    old_ids = sorted(r.id for r in _chunk_rows(pipeline_env, doc.id))
    assert len(old_ids) == 2 and doc.status == DocumentStatus.COMPLETED

    # 替换：覆盖 source、version+1、status 置回 1（Task 11 PUT /file 的行为契约）
    seed_source(doc, make_docx_bytes([
        ("第一章", ["新版内容一。"]), ("第二章", ["新版内容二。"]), ("第三章", ["新版内容三。"]),
    ]))
    doc.version = 2
    doc.status = DocumentStatus.UPLOADED
    pipeline_env.session.commit()

    process_doc(doc.id)

    rows = _chunk_rows(pipeline_env, doc.id)
    assert len(rows) == 3  # 新版本切块入库
    assert {r.id for r in rows}.isdisjoint(old_ids)  # MySQL 全新 ids
    assert sorted(pipeline_env.vector.deleted_ids) == old_ids  # 恰按旧 ids 精准删除
    assert all(oid not in pipeline_env.vector._rows for oid in old_ids)
    assert doc.status == DocumentStatus.COMPLETED
    assert doc.chunk_count == 3
    assert pipeline_env.vector.count_by_doc(doc.id) == 3


def test_web_document(pipeline_env, make_document, monkeypatch, process_doc):
    """网页文档：抓取+抽取的 html 快照落存储 oss_key，md 正常切块完成。"""
    from app.services import pipeline as pipeline_module

    html = "<html><body><h1>网页标题</h1><p>网页正文内容，足够长以供切块使用。</p></body></html>".encode()
    md = "# 网页标题\n\n" + "网页正文内容。" * 50
    monkeypatch.setattr(
        pipeline_module, "fetch_and_extract", lambda url, timeout=30.0: (html, md)
    )
    doc = make_document(source_type=SourceType.WEBPAGE, file_type="html")

    process_doc(doc.id)

    assert doc.status == DocumentStatus.COMPLETED
    assert pipeline_env.storage.get_bytes(doc.oss_key) == html  # html 快照已存
    rows = _chunk_rows(pipeline_env, doc.id)
    assert len(rows) >= 1 and all(r.vectorized for r in rows)
    assert pipeline_env.vector.count_by_doc(doc.id) == len(rows)


def test_run_pending_processes_uploaded_and_isolates_failures(
    pipeline_env, make_document, seed_source, process_doc, run_pending
):
    """run_pending：处理全部 status==1 并返回处理数；单个失败（→7）不影响后续。"""
    ok_doc = make_document(name="健康文档")
    seed_source(ok_doc, make_docx_bytes([("标题", ["正常完成的正文内容。"])]))
    bad_doc = make_document(name="坏文档", file_type="pdf")
    seed_source(bad_doc, _make_pdf([""]))  # 扫描件 → 7
    # 已完成的第三条文档不参与重跑
    done = make_document(name="已完成文档")
    seed_source(done, make_docx_bytes([("标题", ["早已完成的正文内容。"])]))
    process_doc(done.id)
    assert done.status == DocumentStatus.COMPLETED

    n = run_pending()

    # run_pending 内部用 factory 另起的 session 处理并提交——
    # expire_on_commit=False 下本 session 缓存对象已陈旧，回库取真值再断言
    pipeline_env.session.expire_all()

    assert n == 2  # 只处理两条 status==1
    assert ok_doc.status == DocumentStatus.COMPLETED
    assert bad_doc.status == DocumentStatus.FAILED
    assert "扫描件" in (bad_doc.status_reason or "")
    assert done.status == DocumentStatus.COMPLETED  # 已完成不被重跑


def test_precleanup_failure_folds_to_7(
    pipeline_env, make_document, seed_source, process_doc, monkeypatch
):
    """前导清残留失败（如 Milvus 宕机）→ 折叠 status=7 + reason，异常不逸出（Important #1）。

    契约（模块 docstring）：任一步异常 → 7。若 delete_by_doc 在 try 外抛出，
    异常会逸出 process_document 且文档永远卡在 status=1。
    """
    doc = make_document()
    seed_source(doc, make_docx_bytes([("标题", ["正常正文内容。"])]))

    def _boom(doc_id: int) -> None:
        raise RuntimeError("milvus unavailable")

    monkeypatch.setattr(pipeline_env.vector, "delete_by_doc", _boom)
    process_doc(doc.id)  # 异常必须被折叠，不得逸出

    assert doc.status == DocumentStatus.FAILED
    assert "milvus unavailable" in (doc.status_reason or "")


def test_embedder_failure_retry_closes_loop(
    pipeline_env, make_document, seed_source, process_doc, monkeypatch
):
    """真实中间态失败注入（红线 4，Important #2）：向量化阶段 embedder 崩 → 7 且
    chunk 行残留（status=4 已提交）；retry（7→1，Task 11 语义）清残留后从头执行成功。"""
    doc = make_document()
    seed_source(doc, make_docx_bytes([("甲节", ["内容甲。"]), ("乙节", ["内容乙。"])]))
    real_embed = pipeline_env.embedder.embed
    failed = {"once": False}

    def _flaky(texts):
        if not failed["once"]:
            failed["once"] = True
            raise RuntimeError("embedding api 503")
        return real_embed(texts)

    monkeypatch.setattr(pipeline_env.embedder, "embed", _flaky)
    process_doc(doc.id)

    # 失败折叠：status=7，chunk 行残留（红线 4 的真实中间态，非手工预置）
    assert doc.status == DocumentStatus.FAILED
    leftover = _chunk_rows(pipeline_env, doc.id)
    assert len(leftover) == 2 and all(not r.vectorized for r in leftover)
    assert pipeline_env.vector.count_by_doc(doc.id) == 0  # 向量未入库

    # retry：Task 11 将 7 置回 1（version 不动）；embedder 已恢复（flaky 只崩一次）
    doc.status = DocumentStatus.UPLOADED
    pipeline_env.session.commit()
    process_doc(doc.id)

    assert doc.status == DocumentStatus.COMPLETED
    rows = _chunk_rows(pipeline_env, doc.id)
    assert len(rows) == 2  # 残留已清，无重复行
    assert all(r.vectorized for r in rows)
    assert pipeline_env.vector.count_by_doc(doc.id) == 2
    assert doc.chunk_count == 2


def test_replace_old_vectors_served_until_new_inserted(
    pipeline_env, make_document, seed_source, process_doc, monkeypatch
):
    """替换期间不断供（spec §6.1，Important #3）：清旧被调时新向量必须已在库、
    旧向量仍在线——钉死「先插新后删旧」顺序，防挪动顺序后测试静默全绿。"""
    doc = make_document()
    seed_source(doc, make_docx_bytes([("初版", ["初版内容。"])]))
    process_doc(doc.id)
    old_ids = [r.id for r in _chunk_rows(pipeline_env, doc.id)]
    assert doc.status == DocumentStatus.COMPLETED

    seed_source(doc, make_docx_bytes([
        ("新版一", ["新版内容一。"]), ("新版二", ["新版内容二。"]),
    ]))
    doc.version = 2
    doc.status = DocumentStatus.UPLOADED
    pipeline_env.session.commit()

    real_delete = pipeline_env.vector.delete_by_ids
    seen: dict[str, bool] = {}

    def _spy(ids):
        new_rows = [r for r in _chunk_rows(pipeline_env, doc.id) if r.id not in set(old_ids)]
        seen["new_ready"] = bool(new_rows) and all(
            r.id in pipeline_env.vector._rows for r in new_rows
        )
        seen["old_still_serving"] = all(oid in pipeline_env.vector._rows for oid in old_ids)
        return real_delete(ids)

    monkeypatch.setattr(pipeline_env.vector, "delete_by_ids", _spy)
    process_doc(doc.id)

    assert doc.status == DocumentStatus.COMPLETED
    assert seen.get("new_ready") is True  # 删旧前新向量已可检索（先插后删）
    assert seen.get("old_still_serving") is True  # 删旧动作发生时旧向量一直在线


def test_embedder_count_mismatch_fails_loudly(
    pipeline_env, make_document, seed_source, process_doc, monkeypatch
):
    """embedder 返回向量数与切块数不符 → 响亮失败 7（Minor #4）：zip 静默截断
    会造成「部分 chunk 无向量仍标记完成」，必须拒绝。"""
    doc = make_document()
    seed_source(doc, make_docx_bytes([("甲节", ["内容甲。"]), ("乙节", ["内容乙。"])]))
    real_embed = pipeline_env.embedder.embed

    def _short(texts):
        return real_embed(texts)[:-1]  # 少返一条，模拟上游缺行

    monkeypatch.setattr(pipeline_env.embedder, "embed", _short)
    process_doc(doc.id)

    assert doc.status == DocumentStatus.FAILED
    assert "向量" in (doc.status_reason or "") and "2" in (doc.status_reason or "")
    assert pipeline_env.vector.count_by_doc(doc.id) == 0  # 截断数据未入库


def test_empty_document_fails_loudly(pipeline_env, make_document, seed_source, process_doc):
    """空内容文档（解析 ok 但 0 切块）→ 响亮失败 7（Minor #5）：静默完成
    （status=6 + chunk_count=0）会污染 KB 且用户无感知。"""
    doc = make_document()
    seed_source(doc, make_docx_bytes([]))  # 空 docx：解析 ok、md 为空、0 切块

    process_doc(doc.id)

    assert doc.status == DocumentStatus.FAILED
    assert "空" in (doc.status_reason or "")
    assert _chunk_rows(pipeline_env, doc.id) == []
    assert pipeline_env.vector.count_by_doc(doc.id) == 0


def test_embed_batching_follows_settings_batch_size(
    pipeline_env, make_document, seed_source, process_doc, monkeypatch
):
    """按 settings.embedding_batch_size 分批调 embedder（批次对位不串行错位）。"""
    pipeline_env.settings.embedding_batch_size = 1
    doc = make_document()
    seed_source(doc, make_docx_bytes([
        ("甲节", ["内容甲。"]), ("乙节", ["内容乙。"]),
    ]))
    calls: list[list[str]] = []
    real_embed = pipeline_env.embedder.embed

    def _spy(texts):
        calls.append(list(texts))
        return real_embed(texts)

    monkeypatch.setattr(pipeline_env.embedder, "embed", _spy)

    process_doc(doc.id)

    assert doc.status == DocumentStatus.COMPLETED
    rows = _chunk_rows(pipeline_env, doc.id)
    assert len(rows) == 2
    assert [len(c) for c in calls] == [1, 1]  # batch_size=1 → 逐条一批
    assert pipeline_env.vector._rows[rows[0].id].chunk_text == rows[0].content  # 向量对位正确
