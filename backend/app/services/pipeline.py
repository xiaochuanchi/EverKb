"""处理管线（Plan 1 Task 10）：状态机 + 幂等清残留 + 替换语义。

流程（顺序钉死，spec = 设计文档 §6.1 硬约束）：
  载入 doc → [模式判定] → status=2 → 取内容（文件 get_bytes / 网页 fetch_and_extract
  + html 快照）→ parser.parse → md 落存储 status=3 → chunk_markdown 插行 status=4
  → 分批 embed → vector.insert → vectorized status=5 → [替换收尾：按 old_ids 清旧]
  → chunk_count、status=6 提交。任一步异常：status=7 + reason（截 500 字）。
  前导（模式判定/清残留）同样在 try 内：Milvus 宕机等前导故障也折叠为 7，
  未提交的清理动作随 rollback 撤销。空文档（0 切块）与 embed 返回数
  不符 → PipelineError，同样折叠为 7，绝不静默完成。

幂等与替换语义（红线 2/4，模式判定见 _is_replace）：
  - 未完成过（非替换进入）：开头清残留 chunk 行 + vector.delete_by_doc 后从头执行
  - 已有完成版本的替换：先记录 old_ids，全新入库成功后才 vector.delete_by_ids + 删旧行
    （替换期间旧版本向量持续供检索）
"""
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.storage import StorageClient
from app.models import Chunk, Document, DocumentStatus, SourceType, SpanType
from app.parsers import get_parser
from app.parsers.webpage import fetch_and_extract
from app.services.chunking import chunk_markdown, estimate_tokens
from app.services.embedding import Embedder
from app.services.trace import Tracer
from app.services.vector import VectorClient, VectorRow

_REASON_MAX_CHARS = 500  # status_reason 列 String(512)，异常摘要截 500 字

# 管线 Trace 的 trace_id 命名空间：用负数空间与 qa_record.id（正整数）隔离，
# 避免入库链路 span 与问答链路 span 的 trace_id 碰撞（TraceSpan.trace_id 语义
# 一期强绑定 qa_record.id）。入库 trace_id = -(doc_id)。
_PIPELINE_TRACE_ID_OFFSET = -1


class PipelineError(Exception):
    """管线业务失败（解析 ok=False / 空文档 / 向量数不符）；消息原样写入 status_reason。"""


def content_key_for(oss_key: str) -> str:
    """source 对象路径 → content.md 路径（同目录约定）。"""
    return oss_key.rsplit("/", 1)[0] + "/content.md"


def process_document(
    session: Session,
    doc_id: int,
    *,
    storage: StorageClient,
    embedder: Embedder,
    vector: VectorClient,
    settings: Settings,
    tracer: Tracer | None = None,
) -> None:
    """单文档全流程处理：状态机推进到 6，任一步失败折叠为 7 + reason。

    tracer 非空时（二期 Task 29），管线各阶段（parse/chunking/embedding/
    vector_insert）埋 span 供 admin Trace 查看器观测；观测写库失败绝不打断
    入库（Tracer.flush 内部 try/except 吞掉，且失败态下 span 随事务回滚）。
    """
    doc = session.get(Document, doc_id)
    if doc is None:
        raise ValueError(f"文档不存在：doc_id={doc_id}")

    # 管线观测：独立 trace_id 命名空间（负数），与问答 qa_record.id 隔离
    observe = tracer is not None
    if observe:
        tracer.start(_PIPELINE_TRACE_ID_OFFSET * doc_id)

    try:
        # ── 模式判定（进入时一次性读取；前导失败同样折叠为 7，不逸出）──
        entry_status = doc.status
        is_replace = _is_replace(session, doc)
        old_ids: list[int] = []
        if is_replace:
            # 已有完成版本：先记录旧 ids，成功后精准清旧（红线 2）
            old_ids = [
                rid for (rid,) in session.query(Chunk.id).filter(Chunk.document_id == doc_id)
            ]
        else:
            # 未完成过：开头清残留（红线 4，spec §6.1「开头清理后从头执行」）；
            # 在 try 内执行——delete_by_doc 崩（如 Milvus 宕机）→ rollback + 折叠 7，
            # 未提交的 chunk 批量 DELETE 一并回滚，不留半开事务给调用方
            session.query(Chunk).filter(Chunk.document_id == doc_id).delete()
            vector.delete_by_doc(doc_id)

        # ── 取内容：编辑续跑（status==3）直接读已落库的 content.md，跳过解析；
        #    其余从源走：文件读存储；网页抓取 + html 快照落存储 ──────────
        if entry_status == DocumentStatus.EXTRACTED:
            md = storage.get_bytes(content_key_for(doc.oss_key)).decode("utf-8")
        else:
            doc.status = DocumentStatus.PARSING
            session.commit()

            if doc.source_type == SourceType.WEBPAGE:
                if observe:
                    with tracer.span("parser.webpage", SpanType.PARSE, parent_id=None) as parse_span:
                        parse_span.set_input_summary(doc.source_url)
                        html, md = fetch_and_extract(doc.source_url)  # 网络异常由 except 折叠为 7
                        parse_span.set_output_summary(f"md={len(md)} chars")
                else:
                    html, md = fetch_and_extract(doc.source_url)
                storage.put_bytes(doc.oss_key, html)
            else:
                data = storage.get_bytes(doc.oss_key)
                if observe:
                    with tracer.span("parser.parse", SpanType.PARSE, parent_id=None) as parse_span:
                        parse_span.set_input_summary(doc.oss_key.rsplit("/", 1)[-1])
                        result = get_parser(doc.file_type).parse(data, doc.oss_key.rsplit("/", 1)[-1])
                        if not result.ok:
                            raise PipelineError(result.reason or "解析失败")
                        md = result.markdown
                        parse_span.set_output_summary(f"md={len(md)} chars")
                else:
                    result = get_parser(doc.file_type).parse(data, doc.oss_key.rsplit("/", 1)[-1])
                    if not result.ok:
                        raise PipelineError(result.reason or "解析失败")
                    md = result.markdown

            # ── md 落存储，status=3 ────────────────────────────────
            storage.put_bytes(content_key_for(doc.oss_key), md.encode("utf-8"))
            doc.status = DocumentStatus.EXTRACTED
            session.commit()

        # ── 切块入库，status=4 ─────────────────────────────────────
        if observe:
            with tracer.span("chunking", SpanType.CHUNKING, parent_id=None) as chunk_span:
                drafts = chunk_markdown(
                    md, target=settings.chunk_target_chars, overlap=settings.chunk_overlap_chars
                )
                chunk_span.set_output_summary(f"chunks={len(drafts)}")
        else:
            drafts = chunk_markdown(
                md, target=settings.chunk_target_chars, overlap=settings.chunk_overlap_chars
            )
        if not drafts:
            # 空文档响亮失败（Minor #5 裁定）：与扫描件/空网页同形态 → 7，
            # 拒绝 status=6 + 0 chunk 静默完成污染 KB
            raise PipelineError("文档内容为空：解析成功但无可切块内容")
        new_chunks = [
            Chunk(
                document_id=doc.id,
                kb_id=doc.kb_id,
                chunk_index=d.chunk_index,
                page_number=d.page_number,
                content=d.content,
                token_count=estimate_tokens(d.content),
                vectorized=False,
            )
            for d in drafts
        ]
        session.add_all(new_chunks)
        doc.status = DocumentStatus.CHUNKED
        session.commit()

        # ── 分批向量化 + 入 Milvus，status=5 ───────────────────────
        texts = [c.content for c in new_chunks]
        vectors: list[list[float]] = []
        batch = max(1, settings.embedding_batch_size)  # 防 0/负值零步长（Task 8 遗留点，接配置处守卫）
        if observe:
            with tracer.span("embedding", SpanType.EMBEDDING, parent_id=None) as emb_span:
                for i in range(0, len(texts), batch):
                    vectors.extend(embedder.embed(texts[i : i + batch]))
                emb_span.set_output_summary(f"vectors={len(vectors)}")
        else:
            for i in range(0, len(texts), batch):
                vectors.extend(embedder.embed(texts[i : i + batch]))
        if len(vectors) != len(texts):
            # 响亮失败守卫（Minor #4）：zip 会静默截断，缺向量的 chunk 照常
            # 标记 vectorized 完成——拒绝（与「失败要响」先例一致）
            raise PipelineError(
                f"向量化返回数与切块数不符：{len(vectors)} != {len(texts)}"
            )
        # ── 并发守卫（终审 Critical #1 / Important #2）：insert 前现读 doc 行。
        # status=4 已 commit，本 SELECT 开新事务才看得到他方提交；raw 列 SELECT
        # 绕过 identity map 缓存，避免读到过期 enabled / 漏判删除。
        fresh = session.execute(
            select(Document.status, Document.enabled).where(Document.id == doc_id)
        ).first()
        if fresh is None:
            # 处理期间被 API 删除：丢弃本次处理，绝不插入孤儿可搜向量（红线 3）
            session.rollback()
            return
        _, enabled_now = fresh
        insert_rows = [
            VectorRow(
                id=c.id,
                vector=v,
                chunk_text=c.content,
                page_number=c.page_number,
                doc_id=doc.id,
                kb_id=doc.kb_id,
                enabled=enabled_now,
            )
            for c, v in zip(new_chunks, vectors)
        ]
        if observe:
            with tracer.span("vector.insert", SpanType.VECTOR_INSERT, parent_id=None) as ins_span:
                vector.insert(insert_rows)
                ins_span.set_output_summary(f"rows={len(insert_rows)}")
        else:
            vector.insert(insert_rows)
        # insert 后复查：删除落在现读与 insert 之间时，补偿清掉刚插入的向量
        if session.execute(
            select(Document.id).where(Document.id == doc_id)
        ).first() is None:
            vector.delete_by_doc(doc_id)
            session.rollback()
            return
        for c in new_chunks:
            c.vectorized = True
        doc.status = DocumentStatus.VECTORIZING
        session.commit()

        # ── 替换收尾：成功后按 old_ids 精准清旧向量与旧行（红线 2）──
        if is_replace and old_ids:
            vector.delete_by_ids(old_ids)
            session.query(Chunk).filter(Chunk.id.in_(old_ids)).delete(synchronize_session=False)

        doc.chunk_count = len(new_chunks)
        doc.status = DocumentStatus.COMPLETED
        doc.status_reason = None  # 清掉历史失败原因（重试成功场景）
        session.commit()
        # 观测 span 落库（尽力而为）：flush 内部吞异常，此处再包一层双保险，
        # 观测失败绝不打断已完成入库（红线：观测不阻塞主流程）
        if observe:
            try:
                tracer.flush(session)
            except Exception:  # noqa: BLE001 —— 观测写库失败必须吞掉
                pass
    except Exception as e:  # 宽捕获转失败态（Task 8 移交裁定：管线兜底是本层责任）
        session.rollback()
        # identity-map 缓存不可信：session.get 命中已删行的缓存实例时，commit 会
        # 触发 StaleDataError 逸出（终审 Critical #1 实证）。Core UPDATE 按主键
        # 直改，rowcount 兼任存在性判定：行已消失 → 静默退出，绝不残留向量。
        probe = session.execute(
            select(Document.id).where(Document.id == doc_id)
        ).first()
        if probe is None:
            # 处理期间行被 API 删除：无行可折叠，静默退出
            return
        result = session.execute(
            update(Document)
            .where(Document.id == doc_id)
            .values(
                status=DocumentStatus.FAILED,
                status_reason=(str(e) or type(e).__name__)[:_REASON_MAX_CHARS],
            )
        )
        session.commit()
        session.expire_all()  # Core 写绕过 ORM：过期本会话缓存，调用方读到真值
        if result.rowcount == 0:
            # 行在 probe 与 UPDATE 之间又被删：删除已收敛，无需补偿
            return


def run_pending(
    session_factory,
    *,
    storage: StorageClient,
    embedder: Embedder,
    vector: VectorClient,
    settings: Settings,
    tracer: Tracer | None = None,
) -> int:
    """处理所有 status∈(1, 3) 的文档，返回处理数；单个失败不影响后续。

    1 = 上传/重试/替换待处理；3 = md 编辑续跑（PUT /content 置回 3，
    处理从切块阶段开始）。全流程对两者一致，process_document 内部分支。
    tracer 透传给 process_document（每个文档一个独立入库 trace）。
    """
    with session_factory() as session:
        ids = [
            rid
            for (rid,) in session.query(Document.id)
            .filter(Document.status.in_((DocumentStatus.UPLOADED, DocumentStatus.EXTRACTED)))
            .order_by(Document.id)
        ]
    processed = 0
    for doc_id in ids:
        with session_factory() as session:
            try:
                process_document(
                    session, doc_id,
                    storage=storage, embedder=embedder, vector=vector, settings=settings,
                    tracer=tracer,
                )
                processed += 1
            except Exception:  # 业务异常已被 process_document 折叠；此处兜基础设施故障
                continue
    return processed


def _is_replace(session: Session, doc: Document) -> bool:
    """替换模式判定（Ruling，见 ledger Task 10）。

    - 进入时 status==6：直接对完成态文档重跑（计划原文路径）。
    - 进入时 status==1 且 version>1：Task 11 PUT /file（替换）已覆盖 source、
      version+1、status 置回 1——旧完成版 chunk 仍在库中，须保持供检索，
      成功后按 ids 清旧。
    - retry（7→1）不动 version：version==1 走清残留分支（红线 4）；
      version>1 的替换失败 retry 仍走替换分支，保旧版持续供检索。
    - 进入时 status==3 且已有 chunk 行：md 编辑续跑（PUT /content 置回 3），
      chunk 必来自此前完成版本——同样走替换分支保旧版供检索。
    """
    if doc.status == DocumentStatus.COMPLETED:
        return True
    if doc.status == DocumentStatus.EXTRACTED:
        has_chunks = (
            session.query(Chunk.id).filter(Chunk.document_id == doc.id).first() is not None
        )
        return has_chunks
    return doc.status == DocumentStatus.UPLOADED and doc.version > 1
