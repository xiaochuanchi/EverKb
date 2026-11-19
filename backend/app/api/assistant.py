"""admin 侧智能助手问答 API（Task：机器人抽屉真问答，挂载 /api/v1/admin/assistant）。

定位：管理员在后台右上角抽屉里「模拟提问」看效果——切换应用、发 query、
观察检索命中与引用，等价于以某个应用的视角问一次，但不走 open 侧 X-API-Key。

与 open.py 的 chat 差异（复用同一检索/生成/落库链路，见 open.py）：
- 鉴权：require_admin（JWT = 人）而非 X-API-Key（应用）；
- app 来源：请求体显式传 app_id（管理员可切任意应用），不做 key↔app 强绑定；
- 不限流：管理员内部调试场景，不走 check_rate_limit；
- 落库：qa_record.is_admin = True（区分管理员模拟，供统计/追溯隔离），
  同样落 trace_span 成树（管理员要看检索链路）；
- user_key：固定 "admin"（管理员无最终用户标识概念）。

chat 端点显式 response_class=StreamingResponse 退出 EnvelopeRoute（流式不包信封）。
"""
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth import require_admin
from app.api.open import _model_snapshot, _persist, _render_prompt, _sse
from app.core.db import get_db
from app.models import AdminUser, App, Document, QaRecord, SpanType
from app.schemas import AssistantChatRequest
from app.services.llm import ChatMessage
from app.services.rag import build_context, retrieve
from app.services.trace import Tracer

router = APIRouter(prefix="/assistant", tags=["智能助手"])

_ADMIN_USER_KEY = "admin"


def _get_app_or_404(db: Session, app_id: int) -> App:
    """按请求体 app_id 取应用；不存在 404。管理员可切任意应用（含停用，便于调试）。"""
    app = db.get(App, app_id)
    if app is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="应用不存在")
    return app


@router.post("/chat")
def chat(
    payload: AssistantChatRequest,
    request: Request,
    _admin: AdminUser = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """管理员模拟问答（SSE 流式）：按请求体 app_id 检索并流式生成，落 is_admin 记录。"""
    app = _get_app_or_404(db, payload.app_id)
    state = request.app.state
    embedder = state.embedder
    vector = state.vector
    llm = state.llm
    bm25 = getattr(state, "bm25", None)

    # ── 先插 qa_record 拿 id（is_admin=True，answer 暂空），trace_id = qa_record.id ──
    record = QaRecord(
        app_id=app.id,
        is_admin=True,
        user_key=_ADMIN_USER_KEY,
        question=payload.question,
        answer="",
        grounded=True,
        chunk_ids=[],
        doc_ids=[],
        scores=[],
        citations=[],
        model_snapshot=_model_snapshot(state.settings),
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    tracer = Tracer()
    tracer.start(record.id)

    # ── 检索（embedding → retrieval → db 三个 span 成链，对齐 open.py）────────
    parent_id = None
    try:
        with tracer.span("gen_ai.embedding", SpanType.EMBEDDING, parent_id=parent_id) as es:
            es.set_input_summary(payload.question)
            query_vector = embedder.embed([payload.question])[0]
            es.set_output_summary(f"dim={len(query_vector)}")
        parent_id = es.span_id

        with tracer.span("milvus.search", SpanType.RETRIEVAL, parent_id=parent_id) as rs:
            rs.set_input_summary(f"kb_ids={app.kb_ids}, top_k={app.top_k}, mode={app.retrieval_mode}")
            hits = retrieve(query_vector, vector, db, app, query=payload.question, bm25=bm25)
            rs.set_output_summary(f"hits={len(hits)}")
        parent_id = rs.span_id

        with tracer.span("mysql.fetch_docs", SpanType.DB, parent_id=parent_id) as ds:
            doc_ids = {h.doc_id for h in hits}
            docs = list(db.scalars(select(Document).where(Document.id.in_(doc_ids))).all()) if doc_ids else []
            ds.set_output_summary(f"docs={len(docs)}")
        parent_id = ds.span_id
    except Exception:
        # 检索阶段异常：置 grounded=false 走自由回答，不打断问答
        hits, docs = [], []

    context, citations = build_context(hits, docs)
    grounded = len(hits) > 0

    # ── 生成（llm span 流式）────────────────────────────────────
    prompt = _render_prompt(app, context, payload.question)
    messages = [ChatMessage(role="user", content=prompt)]
    temperature = getattr(state.settings, "llm_temperature", 0.3)

    def generate():
        answer_parts: list[str] = []
        try:
            with tracer.span("gen_ai.chat", SpanType.LLM, parent_id=parent_id) as ls:
                ls.set_input_summary(prompt[:500])
                for chunk in llm.chat_stream(messages, temperature=temperature):
                    if chunk.delta:
                        answer_parts.append(chunk.delta)
                        yield _sse({"delta": chunk.delta})
                    if chunk.finish:
                        ls.set_output_summary("".join(answer_parts)[:500])
        except Exception as e:
            # LLM 异常：流已中断，尽力落库失败态（不抛，SSE 已开始）
            answer_parts.append(f"[生成失败: {e}]")
        answer = "".join(answer_parts)
        # 收尾事件 + 落库（在生成器末尾，保证流结束后才写库）
        yield _sse({"grounded": grounded, "citations": citations})
        _persist(db, record, tracer, answer, grounded, citations, hits)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
