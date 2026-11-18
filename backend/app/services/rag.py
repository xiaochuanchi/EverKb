"""检索编排服务（Task 20）：问答链路的 retrieve + build_context。

问答链路（设计文档 §6.3）固定顺序手写，不引 LangChain/LangGraph：
1. 【span: embedding】问题 embed（由编排层在 embedding span 内完成，产出 query_vector）；
2. 【span: retrieval】Milvus search（kb_ids / top_k / threshold）；
3. 【span: db】二次确认 doc 存在且 enabled（防孤儿向量 / 停用文档误引）；
4. chunk 正文 + 引用编号拼 Prompt 上下文，产出 citations。

因此 retrieve 接收「已嵌入的 query_vector」而非问题文本——embed 是独立 span，
藏进 retrieve 会破坏 Span 边界的可观测性。

citations 字段契约（下发给前端 + qa_record 落库快照，防重切后断链）：
doc_name / doc_id / chunk_id / page_number / snippet / score / source_url。
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import App, Document
from app.services.vector import SearchHit

# snippet 截断长度：引用卡片只展示开头，正文全文在上下文中
_SNIPPET_MAX_CHARS = 200

# 系统默认 Prompt 模板（app.prompt_template 为 NULL 时使用）
# 占位符：{context} 引用编号上下文、{question} 用户问题
DEFAULT_PROMPT_TEMPLATE = (
    "你是一个知识库问答助手。请仅根据以下参考资料回答用户问题，"
    "并在引用资料时标注编号（如 [1]）。如果参考资料不足以回答，请如实说明。\n\n"
    "参考资料：\n{context}\n\n"
    "用户问题：{question}"
)


def retrieve(
    query_vector: list[float],
    vector,
    db: Session,
    app: App,
) -> list[SearchHit]:
    """按已嵌入的问题向量检索，二次确认 doc 存在且 enabled，返回有效命中。

    query_vector 由编排层在 embedding span 内产出（embed 是独立 span）。
    零命中 / 全部被过滤 → 空列表（编排层据此走 grounded=false 自由回答分支）。
    """
    if not app.kb_ids:
        return []
    hits = vector.search(
        query_vector,
        app.kb_ids,
        top_k=app.top_k,
        threshold=float(app.score_threshold) if app.score_threshold is not None else None,
    )
    if not hits:
        return []
    # 二次确认：命中 chunk 的 doc 必须存在且 enabled（防删除/停用后孤儿向量误引）
    doc_ids = {h.doc_id for h in hits}
    docs = db.scalars(select(Document).where(Document.id.in_(doc_ids))).all()
    valid_ids = {d.id for d in docs if d.enabled}
    return [h for h in hits if h.doc_id in valid_ids]


def build_context(hits: list[SearchHit], docs: list[Document]) -> tuple[str, list[dict]]:
    """chunk 正文 + 引用编号拼 Prompt 上下文；返回 (context, citations)。

    docs 为 hits 涉及文档的去重列表（按 doc_id 可索引），供 citations 填 doc_name/source_url。
    """
    if not hits:
        return "", []
    doc_map = {d.id: d for d in docs}
    parts: list[str] = []
    citations: list[dict] = []
    for idx, hit in enumerate(hits, start=1):
        parts.append(f"[{idx}] {hit.chunk_text}")
        doc = doc_map.get(hit.doc_id)
        citations.append({
            "doc_name": doc.name if doc else "",
            "doc_id": hit.doc_id,
            "chunk_id": hit.chunk_id,
            "page_number": hit.page_number,
            "snippet": _truncate(hit.chunk_text, _SNIPPET_MAX_CHARS),
            "score": hit.score,
            "source_url": doc.source_url if doc else None,
        })
    return "\n\n".join(parts), citations


def _truncate(text: str, limit: int) -> str:
    """按字符数截断（Python 字符串按码点计数，中文友好）。"""
    return text if len(text) <= limit else text[:limit] + "…"
