"""admin 侧智能助手问答 API（机器人抽屉真问答）。

锁定点：
- JWT 鉴权：无 token / 无效 token 401（require_admin 生效）；
- SSE 流式：含 delta 片段 + 收尾 grounded+citations；
- 切换 app_id：管理员可指定任意应用（含停用）模拟提问；
- 落库：qa_record.is_admin=True + trace_span 成树；
- app_id 不存在 404。
"""
import json

from app.models import App, Chunk, Document, DocumentStatus, QaRecord, SourceType, TraceSpan


def _make_app(client, *, kb_ids, name="聊天应用", enabled=True, top_k=5, api_key=None) -> int:
    session = client.app.state.session_factory()
    app = App(name=name, kb_ids=kb_ids, api_key=api_key or f"sk-{name}", enabled=enabled, top_k=top_k, enterprise_id=1)
    session.add(app)
    session.commit()
    session.refresh(app)
    app_id = app.id
    session.close()
    return app_id


def _make_doc_and_hit(client, *, kb_id, doc_id, text="知识库正文内容", enabled=True) -> int:
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


def _stream_assistant(client, app_id: int, question: str):
    """发 admin 助手 chat 请求（默认带 conftest 预置的 Bearer 头），收 SSE，解析 (deltas, final)。"""
    with client.stream(
        "POST",
        "/api/v1/admin/assistant/chat",
        json={"app_id": app_id, "question": question},
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


def test_assistant_chat_streams_delta_and_citations(client):
    """命中：SSE 流含 delta + 收尾 grounded=true + citations。"""
    app_id = _make_app(client, kb_ids=[10])
    _make_doc_and_hit(client, kb_id=10, doc_id=1001)

    answer, final = _stream_assistant(client, app_id, "产品是什么")
    assert answer != ""
    assert final is not None
    assert final["grounded"] is True
    assert len(final["citations"]) >= 1
    c = final["citations"][0]
    assert c["doc_name"] == "测试文档"
    assert c["doc_id"] == 1001
    assert "snippet" in c and "score" in c


def test_assistant_chat_zero_hit_grounded_false(client):
    """零命中：grounded=false，无 citations。"""
    app_id = _make_app(client, kb_ids=[10])
    _, final = _stream_assistant(client, app_id, "无人知道的问题")
    assert final["grounded"] is False
    assert final["citations"] == []


def test_assistant_chat_switches_app(client):
    """管理员可切换 app_id：两个应用各自命中各自的向量。"""
    app_a = _make_app(client, kb_ids=[10], name="应用A")
    app_b = _make_app(client, kb_ids=[20], name="应用B")
    _make_doc_and_hit(client, kb_id=10, doc_id=2001)
    _make_doc_and_hit(client, kb_id=20, doc_id=2002)

    _, final_a = _stream_assistant(client, app_a, "问题A")
    _, final_b = _stream_assistant(client, app_b, "问题B")

    assert final_a["grounded"] is True
    assert final_b["grounded"] is True
    # 各自命中的 doc 不同
    assert {c["doc_id"] for c in final_a["citations"]} == {2001}
    assert {c["doc_id"] for c in final_b["citations"]} == {2002}


def test_assistant_chat_persists_is_admin_record_and_spans(client):
    """落库：qa_record.is_admin=True + trace_span 成树。"""
    app_id = _make_app(client, kb_ids=[10])
    _make_doc_and_hit(client, kb_id=10, doc_id=3001)

    answer, final = _stream_assistant(client, app_id, "落库验证问题")

    session = client.app.state.session_factory()
    rec = session.query(QaRecord).one()
    assert rec.app_id == app_id
    assert rec.is_admin is True
    assert rec.question == "落库验证问题"
    assert rec.answer == answer
    assert rec.grounded is True
    assert rec.user_key == "admin"
    assert 3001 in rec.doc_ids
    assert rec.citations == final["citations"]
    assert rec.latency_ms > 0  # 端到端耗时物化（回归锁定：字段曾有写入缺失恒 0）

    spans = session.query(TraceSpan).filter(TraceSpan.trace_id == rec.id).all()
    assert len(spans) >= 1
    roots = [s for s in spans if s.parent_span_id is None]
    assert len(roots) >= 1
    session.close()


def test_assistant_chat_app_not_found_404(client):
    """app_id 不存在 → 404（信封里 code 404）。"""
    r = client.post(
        "/api/v1/admin/assistant/chat",
        json={"app_id": 999999, "question": "x"},
    )
    assert r.status_code == 404


def test_assistant_chat_requires_auth(client):
    """无 JWT → 401。"""
    r = client.post(
        "/api/v1/admin/assistant/chat",
        json={"app_id": 1, "question": "x"},
        headers={"Authorization": ""},
    )
    assert r.status_code == 401
