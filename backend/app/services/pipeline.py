"""处理管线（Plan 1 Task 10）：状态机 + 幂等清残留 + 替换语义。

流程（顺序钉死，spec = 设计文档 §6.1 硬约束）：
  载入 doc → [模式判定] → status=2 → 取内容（文件 get_bytes / 网页 fetch_and_extract
  + html 快照）→ parser.parse → md 落存储 status=3 → chunk_markdown 插行 status=4
  → 分批 embed → vector.insert → vectorized status=5 → [替换收尾：按 old_ids 清旧]
  → chunk_count、status=6 提交。任一步异常：status=7 + reason（截 500 字）。

幂等与替换语义（红线 2/4，模式判定见 _is_replace）：
  - 未完成过（非替换进入）：开头清残留 chunk 行 + vector.delete_by_doc 后从头执行
  - 已有完成版本的替换：先记录 old_ids，全新入库成功后才 vector.delete_by_ids + 删旧行
    （替换期间旧版本向量持续供检索）
"""
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.storage import StorageClient
from app.models import Chunk, Document, DocumentStatus, SourceType
from app.parsers import get_parser
from app.parsers.webpage import fetch_and_extract
from app.services.chunking import chunk_markdown, estimate_tokens
from app.services.embedding import Embedder
from app.services.vector import VectorClient, VectorRow

_REASON_MAX_CHARS = 500  # status_reason 列 String(512)，异常摘要截 500 字


class PipelineError(Exception):
    """管线业务失败（如解析 ok=False）；消息原样写入 document.status_reason。"""


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
) -> None:
    """单文档全流程处理：状态机推进到 6，任一步失败折叠为 7 + reason。"""
    doc = session.get(Document, doc_id)
    if doc is None:
        raise ValueError(f"文档不存在：doc_id={doc_id}")

    # ── 模式判定（进入时一次性读取）──────────────────────────────
    is_replace = _is_replace(session, doc)
    old_ids: list[int] = []
    if is_replace:
        # 已有完成版本：先记录旧 ids，成功后精准清旧（红线 2）
        old_ids = [
            rid for (rid,) in session.query(Chunk.id).filter(Chunk.document_id == doc_id)
        ]
    else:
        # 未完成过：开头清残留（红线 4，spec §6.1「开头清理后从头执行」）
        session.query(Chunk).filter(Chunk.document_id == doc_id).delete()
        vector.delete_by_doc(doc_id)

    try:
        doc.status = DocumentStatus.PARSING
        session.commit()

        # ── 取内容：文件读存储；网页抓取 + html 快照落存储 ──────────
        if doc.source_type == SourceType.WEBPAGE:
            html, md = fetch_and_extract(doc.source_url)  # 网络异常由 except 折叠为 7
            storage.put_bytes(doc.oss_key, html)
        else:
            data = storage.get_bytes(doc.oss_key)
            result = get_parser(doc.file_type).parse(data, doc.oss_key.rsplit("/", 1)[-1])
            if not result.ok:
                raise PipelineError(result.reason or "解析失败")
            md = result.markdown

        # ── md 落存储，status=3 ────────────────────────────────────
        storage.put_bytes(content_key_for(doc.oss_key), md.encode("utf-8"))
        doc.status = DocumentStatus.EXTRACTED
        session.commit()

        # ── 切块入库，status=4 ─────────────────────────────────────
        drafts = chunk_markdown(
            md, target=settings.chunk_target_chars, overlap=settings.chunk_overlap_chars
        )
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
        for i in range(0, len(texts), batch):
            vectors.extend(embedder.embed(texts[i : i + batch]))
        vector.insert([
            VectorRow(
                id=c.id,
                vector=v,
                chunk_text=c.content,
                page_number=c.page_number,
                doc_id=doc.id,
                kb_id=doc.kb_id,
                enabled=doc.enabled,
            )
            for c, v in zip(new_chunks, vectors)
        ])
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
    except Exception as e:  # 宽捕获转失败态（Task 8 移交裁定：管线兜底是本层责任）
        session.rollback()
        doc = session.get(Document, doc_id)
        doc.status = DocumentStatus.FAILED
        doc.status_reason = (str(e) or type(e).__name__)[:_REASON_MAX_CHARS]
        session.commit()


def run_pending(
    session_factory,
    *,
    storage: StorageClient,
    embedder: Embedder,
    vector: VectorClient,
    settings: Settings,
) -> int:
    """处理所有 status==1 的文档，返回处理数；单个失败不影响后续。"""
    with session_factory() as session:
        ids = [
            rid
            for (rid,) in session.query(Document.id)
            .filter(Document.status == DocumentStatus.UPLOADED)
            .order_by(Document.id)
        ]
    processed = 0
    for doc_id in ids:
        with session_factory() as session:
            try:
                process_document(
                    session, doc_id,
                    storage=storage, embedder=embedder, vector=vector, settings=settings,
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
      成功后按 ids 清旧；retry（7→1）不动 version，走清残留分支（红线 4）。
    """
    if doc.status == DocumentStatus.COMPLETED:
        return True
    return doc.status == DocumentStatus.UPLOADED and doc.version > 1
