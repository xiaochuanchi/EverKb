"""open 侧问答 API（Task 21，挂载 /api/v1/apps/{app_id}/*）。

X-API-Key 鉴权（deps.require_api_key）+ chat 限流（deps.check_rate_limit）。

chat 流程（设计文档 §6.3）固定顺序手写，Span 埋点成链：
1. 【span: embedding】问题 embed；
2. 【span: retrieval】Milvus search（kb_ids/top_k/threshold）；
3. 【span: db】doc 二次确认（存在且 enabled）；
4. 【span: llm】chunk 正文+引用编号拼 prompt → 流式生成；
5. SSE 流式返回 delta 片段 + 收尾 grounded/citations；
6. 落 qa_record + trace_span（流结束后批量，失败不打断）。

落库顺序：先插 qa_record 拿 id（answer 暂空）→ trace_id 即 qa_record.id →
流式生成时埋 span → 流结束后回填 answer 等字段 + flush span。

chat 端点显式 response_class=StreamingResponse 退出 EnvelopeRoute（流式不能包信封）。
"""
import json
import time
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import check_rate_limit, require_api_key
from app.core.db import get_db
from app.models import App, Document, Feedback, QaRecord, SpanType
from app.schemas import ChatRequest, FeedbackRequest
from app.services.llm import ChatMessage
from app.services.rag import DEFAULT_PROMPT_TEMPLATE, build_context, retrieve
from app.services.trace import Tracer

router = APIRouter(prefix="/apps", tags=["问答"])


def _get_matching_app(app: App, app_id: int) -> App:
    """URL 的 app_id 必须与 X-API-Key 对应的应用一致（防 A 的 key 访问 B）。"""
    if app.id != app_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="API Key 与应用不匹配")
    return app


@router.post("/{app_id}/chat")
def chat(
    app_id: int,
    payload: ChatRequest,
    request: Request,
    app: App = Depends(check_rate_limit),
    db: Session = Depends(get_db),
):
    """SSE 流式问答（X-API-Key 鉴权 + 限流）。"""
    app = _get_matching_app(app, app_id)
    state = request.app.state
    embedder = state.embedder
    vector = state.vector
    llm = state.llm
    bm25 = getattr(state, "bm25", None)

    # ── 先插 qa_record 拿 id（answer 暂空），trace_id = qa_record.id ──
    record = QaRecord(
        app_id=app.id,
        user_key=payload.user_key,
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

    # ── 检索（embedding → retrieval → db 三个 span 成链）────────
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

        # db span：二次确认已在 retrieve 内完成，这里做 doc 批量查询供 citations
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


@router.post("/{app_id}/feedback")
def feedback(
    app_id: int,
    payload: FeedbackRequest,
    app: App = Depends(require_api_key),
    db: Session = Depends(get_db),
):
    """更新 qa_record.feedback（0 未反馈 / 1 满意 / -1 不满意）。"""
    _get_matching_app(app, app_id)
    record = db.get(QaRecord, payload.record_id)
    if record is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="问答记录不存在")
    if record.app_id != app.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="记录不属于该应用")
    record.feedback = payload.feedback
    db.commit()
    return {"record_id": record.id, "feedback": record.feedback}


# ── 内部辅助 ────────────────────────────────────────────────────


def _sse(data: dict) -> str:
    """SSE data 帧（JSON + 双换行分隔）。"""
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


def _render_prompt(app: App, context: str, question: str) -> str:
    """按 app.prompt_template（或系统默认）渲染 Prompt。

    兜底：若自定义模板缺失 {question}/{context} 占位符（历史脏数据），回退系统默认模板，
    防止上下文与问题无法注入、LLM 收到残缺 prompt。
    """
    template = app.prompt_template or DEFAULT_PROMPT_TEMPLATE
    if "{question}" not in template or "{context}" not in template:
        template = DEFAULT_PROMPT_TEMPLATE
    return template.format(context=context, question=question)


def _model_snapshot(settings) -> dict:
    """模型参数快照：只存 model 名与采样参数，不含 api_key/base_url（决策 §7-7）。"""
    return {
        "model": getattr(settings, "llm_model", ""),
        "temperature": getattr(settings, "llm_temperature", 0.3),
    }


def _persist(db: Session, record: QaRecord, tracer: Tracer, answer: str, grounded: bool, citations: list, hits) -> None:
    """流结束后回填 qa_record + 批量落 trace_span（失败吞掉，不打断已完成的 SSE）。"""
    try:
        record.answer = answer
        record.grounded = grounded
        record.citations = citations
        record.chunk_ids = [h.chunk_id for h in hits]
        record.doc_ids = list({h.doc_id for h in hits})
        record.scores = [h.score for h in hits]
        db.commit()
        tracer.flush(db)
        db.commit()
    except Exception:
        # 观测写库失败不打断问答（模型四次修订纪律）；qa_record 已插，answer 尽力回填
        db.rollback()
