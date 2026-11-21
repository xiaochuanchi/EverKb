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

M1（2026-11-20）改动：摘除 trial 按 token 扣费逻辑——商业化方案决策「M1 摘除
扣费、M2 平移 quota 引擎到 enterprise_wallet 再接回」（设计方案 §10、§11）。
平台账号问答本就是免费，企业侧计费在 M2 落地。
"""
import time
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth import require_admin
from app.api.authz import ensure_enterprise_active, ensure_owned
from app.api.envelope import EnvelopeRoute
from app.api.open import _model_snapshot, _persist, _render_prompt, _sse
from app.core.db import get_db
from app.models import App, Document, QaRecord, SpanType
from app.schemas import AssistantChatRequest, TrialRecordListOut
from app.services.llm import ChatMessage
from app.services.quota import actual_amount, reserve, reserve_amount, refund, settle
from app.services.rag import build_context, retrieve
from app.services.trace import Tracer

# 挂统一信封：/records 返回普通 JSON；/chat 是 StreamingResponse，信封自动放行
router = APIRouter(prefix="/assistant", tags=["智能助手"], route_class=EnvelopeRoute)

_ADMIN_USER_KEY = "admin"


def _get_app_or_404(db: Session, app_id: int, ent_id: int | None) -> App:
    """按请求体 app_id 取应用；企业账号校验归属（跨企业 404），平台账号不限。"""
    app = db.get(App, app_id)
    if app is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="应用不存在")
    if ent_id is not None:
        ensure_owned(db, app, ent_id)
    return app


@router.post("/chat")
def chat(
    payload: AssistantChatRequest,
    request: Request,
    admin=Depends(require_admin),
    db: Session = Depends(get_db),
):
    """后台问答（SSE 流式）：管理员可切任意应用；企业管理员扣企业钱包，平台账号免费。"""
    question = payload.question
    app = _get_app_or_404(db, payload.app_id, admin.enterprise_id)
    state = request.app.state
    embedder = state.embedder
    vector = state.vector
    llm = state.llm
    bm25 = getattr(state, "bm25", None)
    t0 = time.monotonic()  # 端到端计时起点（单调钟测时长，对齐 open.py）

    # ── 冻结拦截（§7）：企业冻结/清理时问答 403，不触 embedding/LLM，零成本 ──
    if admin.enterprise_id is not None:
        ensure_enterprise_active(db, admin.enterprise_id)

    # ── 计费：企业管理员（enterprise_id 非 NULL）扣企业钱包；平台账号免费 ──
    reserved = None
    if admin.enterprise_id is not None:
        reserved = reserve_amount(state.settings, question)
        if not reserve(db, admin.enterprise_id, reserved):
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="企业额度不足，请联系管理员充值")

    user_key = _ADMIN_USER_KEY

    # ── 先插 qa_record 拿 id（is_admin=True，answer 暂空），trace_id = qa_record.id ──
    record = QaRecord(
        app_id=app.id,
        enterprise_id=admin.enterprise_id,
        is_admin=True,
        user_key=user_key,
        question=question,
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
            es.set_input_summary(question)
            query_vector = embedder.embed([question])[0]
            es.set_output_summary(f"dim={len(query_vector)}")
            es.set_tokens(in_tokens=len(question), out_tokens=0)
        parent_id = es.span_id

        with tracer.span("milvus.search", SpanType.RETRIEVAL, parent_id=parent_id) as rs:
            rs.set_input_summary(f"kb_ids={app.kb_ids}, top_k={app.top_k}, mode={app.retrieval_mode}")
            hits = retrieve(query_vector, vector, db, app, query=question, bm25=bm25)
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
    prompt = _render_prompt(app, context, question)
    messages = [ChatMessage(role="user", content=prompt)]
    temperature = getattr(state.settings, "llm_temperature", 0.3)

    def generate():
        answer_parts: list[str] = []
        tokens_in = 0
        tokens_out = 0
        failed = False
        try:
            with tracer.span("gen_ai.chat", SpanType.LLM, parent_id=parent_id) as ls:
                ls.set_input_summary(prompt[:500])
                for chunk in llm.chat_stream(messages, temperature=temperature):
                    if chunk.delta:
                        answer_parts.append(chunk.delta)
                        yield _sse({"delta": chunk.delta})
                    if chunk.finish:
                        # 末帧带厂商回传的真实 usage；没有则按 prompt/答案字符数估算
                        tokens_in = chunk.tokens_in
                        tokens_out = chunk.tokens_out
                        ls.set_tokens(in_tokens=tokens_in, out_tokens=tokens_out)
                        ls.set_output_summary("".join(answer_parts)[:500])
        except Exception as e:
            # LLM 异常：流已中断，尽力落库失败态（不抛，SSE 已开始）
            failed = True
            answer_parts.append(f"[生成失败: {e}]")
        answer = "".join(answer_parts)
        cost = actual_amount(state.settings, question, prompt, answer, tokens_in, tokens_out)
        record.total_cost = Decimal("0") if failed else cost
        # ── 结算：企业管理员失败退预留，成功按真实成本结算 ──
        if reserved is not None:
            if failed:
                refund(db, admin.enterprise_id, reserved)
            else:
                settle(
                    db, admin.enterprise_id, reserved, cost,
                    ref_id=record.id, ref_type="qa_record",
                )
        # 收尾事件 + 落库（在生成器末尾，保证流结束后才写库）
        yield _sse(
            {"grounded": grounded, "citations": citations, "cost": float(record.total_cost or 0)}
        )
        latency_ms = int((time.monotonic() - t0) * 1000)
        _persist(db, record, tracer, answer, grounded, citations, hits, latency_ms)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/records", response_model=TrialRecordListOut)
def my_records(
    limit: int = 50,
    admin=Depends(require_admin),
    db: Session = Depends(get_db),
) -> TrialRecordListOut:
    """查看自己的问答历史（admin 侧记录，按账号企业隔离）。"""
    rows = db.scalars(
        select(QaRecord)
        .where(
            QaRecord.user_key == _ADMIN_USER_KEY,
            QaRecord.enterprise_id == admin.enterprise_id,
        )
        .order_by(QaRecord.id.desc())
        .limit(min(max(limit, 1), 200))
    ).all()
    return TrialRecordListOut(items=rows, total=len(rows))
