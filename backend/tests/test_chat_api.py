"""问答 API（Task 21）：SSE 流式 + 引用 + 落库。

锁定点：
- SSE 流含 delta 片段与收尾 grounded+citations；
- 零命中 grounded=false；停用文档不命中；
- 落库 qa_record 字段完整、trace_span 成树；
- feedback 更新。
"""
import json

from app.models import App, Chunk, Document, DocumentStatus, QaRecord, SourceType, TraceSpan


def _make_app(client, *, kb_ids, api_key="sk-chat-key", top_k=5) -> int:
    session = client.app.state.session_factory()
    app = App(name="聊天应用", kb_ids=kb_ids, api_key=api_key, enabled=True, top_k=top_k)
    session.add(app)
    session.commit()
    session.refresh(app)
    app_id = app.id
    session.close()
    return app_id


def _make_doc_and_hit(client, *, kb_id, doc_id, text="知识库正文内容", enabled=True) -> None:
    """造一个已完成文档 + 一条已启用向量（doc_id 显式指定，便于命中断言）。"""
    session = client.app.state.session_factory()
    doc = Document(
        id=doc_id, kb_id=kb_id, name="测试文档", source_type=SourceType.UPLOAD,
        file_type="md", status=DocumentStatus.COMPLETED, enabled=enabled, chunk_count=1,
    )
    session.add(doc)
    chunk = Chunk(document_id=doc_id, kb_id=kb_id, chunk_index=1, content=text, token_count=5, vectorized=True)
    session.add(chunk)
    session.commit()
    session.close()
    from app.services.vector import VectorRow

    client.app.state.vector.insert([
        VectorRow(id=chunk.id, vector=[1.0] * 8, chunk_text=text, page_number=None,
                  doc_id=doc_id, kb_id=kb_id, enabled=enabled),
    ])
    return chunk.id


def _stream_chat(client, app_id: int, question: str, api_key="sk-chat-key"):
    """发 chat 请求，收 SSE 流，解析出 (deltas, final_event)。"""
    with client.stream(
        "POST",
        f"/api/v1/apps/{app_id}/chat",
        json={"question": question, "user_key": "u1"},
        headers={"X-API-Key": api_key},
    ) as resp:
        assert resp.status_code == 200
        deltas = []
        final = None
        for line in resp.iter_lines():
            if not line or not line.startswith("data: "):
                continue
            payload = json.loads(line[len("data: "):])
            if "delta" in payload:
                deltas.append(payload["delta"])
            else:
                final = payload
        return "".join(deltas), final


def test_chat_streams_delta_and_citations(client):
    """命中：SSE 流含 delta + 收尾 grounded=true + citations。"""
    app_id = _make_app(client, kb_ids=[10])
    _make_doc_and_hit(client, kb_id=10, doc_id=1001)

    answer, final = _stream_chat(client, app_id, "产品是什么")
    assert answer != ""
    assert final is not None
    assert final["grounded"] is True
    assert len(final["citations"]) >= 1
    c = final["citations"][0]
    assert c["doc_name"] == "测试文档"
    assert c["doc_id"] == 1001
    assert c["chunk_id"] is not None
    assert "snippet" in c and "score" in c


def test_chat_zero_hit_grounded_false(client):
    """零命中：grounded=false，无 citations。"""
    app_id = _make_app(client, kb_ids=[10])  # 不造任何向量
    _, final = _stream_chat(client, app_id, "无人知道的问题")
    assert final["grounded"] is False
    assert final["citations"] == []


def test_chat_disabled_doc_not_hit(client):
    """停用文档不命中：grounded=false。"""
    app_id = _make_app(client, kb_ids=[10])
    _make_doc_and_hit(client, kb_id=10, doc_id=1002, enabled=False)
    _, final = _stream_chat(client, app_id, "停用文档的内容")
    assert final["grounded"] is False


def test_chat_persists_qa_record_and_spans(client):
    """落库：qa_record 字段完整 + trace_span 成树。"""
    app_id = _make_app(client, kb_ids=[10])
    _make_doc_and_hit(client, kb_id=10, doc_id=1003)

    answer, final = _stream_chat(client, app_id, "落库验证问题")

    session = client.app.state.session_factory()
    rec = session.query(QaRecord).one()
    assert rec.app_id == app_id
    assert rec.question == "落库验证问题"
    assert rec.answer == answer
    assert rec.grounded is True
    assert rec.user_key == "u1"
    assert 1003 in rec.doc_ids
    assert rec.citations == final["citations"]

    spans = session.query(TraceSpan).filter(TraceSpan.trace_id == rec.id).all()
    assert len(spans) >= 1  # 至少 embedding/retrieval/db/llm 若干 span
    # 根 span parent 为 NULL
    roots = [s for s in spans if s.parent_span_id is None]
    assert len(roots) >= 1
    session.close()


def test_feedback_updates_qa_record(client):
    """feedback 更新 qa_record.feedback。"""
    app_id = _make_app(client, kb_ids=[10])
    _make_doc_and_hit(client, kb_id=10, doc_id=1004)
    _stream_chat(client, app_id, "反馈问题")

    session = client.app.state.session_factory()
    rec_id = session.query(QaRecord).one().id
    session.close()

    r = client.post(
        f"/api/v1/apps/{app_id}/feedback",
        json={"record_id": rec_id, "feedback": -1},
        headers={"X-API-Key": "sk-chat-key"},
    )
    assert r.status_code == 200

    session = client.app.state.session_factory()
    assert session.query(QaRecord).one().feedback == -1
    session.close()


def test_chat_wrong_key_401(client):
    """错 key 401（X-API-Key 鉴权在 open 路由生效）。"""
    app_id = _make_app(client, kb_ids=[10])
    r = client.post(
        f"/api/v1/apps/{app_id}/chat",
        json={"question": "x", "user_key": "u"},
        headers={"X-API-Key": "sk-wrong"},
    )
    assert r.status_code == 401
