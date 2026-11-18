"""问答记录 API（Task 22）。挂载 /api/v1/admin/records。

锁定点：分页 + feedback 筛选 + 详情含 citations。
"""
from app.models import App, Feedback, QaRecord

BASE = "/api/v1/admin/records"


def _seed_record(client, *, app_id, question="问题", feedback=Feedback.NONE, **extra) -> QaRecord:
    session = client.app.state.session_factory()
    rec = QaRecord(
        app_id=app_id,
        user_key="u1",
        question=question,
        answer="回答内容",
        grounded=True,
        chunk_ids=[1, 2],
        doc_ids=[10],
        scores=[0.9, 0.8],
        citations=[{"doc_name": "d", "chunk_id": 1}],
        model_snapshot={"model": "m"},
        feedback=feedback,
        **extra,
    )
    session.add(rec)
    session.commit()
    session.refresh(rec)
    session.close()
    return rec


def _seed_app(client, *, name="记录应用", api_key="sk-rec") -> int:
    session = client.app.state.session_factory()
    app = App(name=name, kb_ids=[], api_key=api_key, enabled=True)
    session.add(app)
    session.commit()
    session.refresh(app)
    app_id = app.id
    session.close()
    return app_id


def test_list_records_paginated(client):
    app_id = _seed_app(client)
    for i in range(5):
        _seed_record(client, app_id=app_id, question=f"问题{i}")
    r = client.get(BASE, params={"page": 1, "size": 2})
    assert r.status_code == 200
    body = r.json()["data"]
    assert body["total"] == 5
    assert body["page"] == 1
    assert body["size"] == 2
    assert len(body["items"]) == 2


def test_list_records_filter_by_app_id(client):
    app_a = _seed_app(client, name="A")
    app_b = _seed_app(client, name="B", api_key="sk-b")
    _seed_record(client, app_id=app_a, question="A的")
    _seed_record(client, app_id=app_b, question="B的")
    r = client.get(BASE, params={"app_id": app_a})
    body = r.json()["data"]
    assert body["total"] == 1
    assert body["items"][0]["question"] == "A的"


def test_list_records_filter_by_feedback(client):
    app_id = _seed_app(client)
    _seed_record(client, app_id=app_id, feedback=Feedback.GOOD)
    _seed_record(client, app_id=app_id, feedback=Feedback.BAD)
    _seed_record(client, app_id=app_id, feedback=Feedback.NONE)
    r = client.get(BASE, params={"feedback": Feedback.BAD})
    body = r.json()["data"]
    assert body["total"] == 1
    assert body["items"][0]["feedback"] == Feedback.BAD


def test_get_record_detail_with_citations(client):
    app_id = _seed_app(client)
    rec = _seed_record(client, app_id=app_id, question="详情问题")
    r = client.get(f"{BASE}/{rec.id}")
    assert r.status_code == 200
    body = r.json()["data"]
    assert body["id"] == rec.id
    assert body["question"] == "详情问题"
    assert body["answer"] == "回答内容"
    assert body["citations"] == [{"doc_name": "d", "chunk_id": 1}]
    assert body["feedback"] == Feedback.NONE


def test_get_record_404(client):
    assert client.get(f"{BASE}/99999").status_code == 404
