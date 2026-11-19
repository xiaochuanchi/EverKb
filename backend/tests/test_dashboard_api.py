"""平台概况 API（dashboard 运营驾驶舱）。挂载 /api/v1/admin/dashboard。

锁定点：计数聚合、近 14 天趋势补零、文档状态分布全枚举、检索模式分布、
最近问答 Top N、累计花费。
"""
from datetime import datetime, timedelta

from app.models import App, Chunk, Document, KnowledgeBase, QaRecord, TraceSpan

BASE = "/api/v1/admin/dashboard"


def _seed_dashboard_data(client):
    """造概况页所需数据：1 库 + 2 文档 + 3 chunk + 2 应用 + 3 问答。"""
    session = client.app.state.session_factory()

    kb = KnowledgeBase(name="kb-a", description="d")
    session.add(kb)
    session.flush()

    d1 = Document(kb_id=kb.id, name="d1.md", file_type="md", file_size=10, status=6)
    d2 = Document(kb_id=kb.id, name="d2.md", file_type="md", file_size=10, status=7)
    session.add_all([d1, d2])
    session.flush()

    session.add_all([
        Chunk(document_id=d1.id, kb_id=kb.id, chunk_index=0, content="c1", token_count=1, vectorized=True),
        Chunk(document_id=d1.id, kb_id=kb.id, chunk_index=1, content="c2", token_count=1, vectorized=True),
        Chunk(document_id=d2.id, kb_id=kb.id, chunk_index=0, content="c3", token_count=1, vectorized=False),
    ])

    app1 = App(name="app-dense", kb_ids=[kb.id], api_key="k1", retrieval_mode="dense")
    app2 = App(name="app-hybrid", kb_ids=[kb.id], api_key="k2", retrieval_mode="hybrid")
    session.add_all([app1, app2])
    session.flush()

    now = datetime.now()
    for i, (q, grounded, cost) in enumerate([
        ("问题A", True, "0.001"),
        ("问题B", False, "0.002"),
        ("问题C", True, "0.003"),
    ]):
        rec = QaRecord(
            app_id=app1.id,
            user_key="u",
            question=q,
            answer="答",
            grounded=grounded,
            latency_ms=100 + i * 10,
            total_cost=cost,
        )
        rec.created_at = now - timedelta(days=i)  # 今天/昨天/前天各一条
        session.add(rec)

    session.commit()
    session.close()


def test_dashboard_counts(client):
    """计数聚合正确。"""
    _seed_dashboard_data(client)
    r = client.get(BASE)
    assert r.status_code == 200
    body = r.json()["data"]

    assert body["kb_count"] == 1
    assert body["doc_count"] == 2
    assert body["chunk_count"] == 3
    assert body["app_count"] == 2
    assert body["qa_count"] == 3
    assert body["failed_doc_count"] == 1  # d2 status=7
    assert abs(body["total_cost"] - 0.006) < 1e-9


def test_dashboard_trend_14_days(client):
    """近 14 天趋势：长度 14，缺失日期补 0，含今天问答数。"""
    _seed_dashboard_data(client)
    r = client.get(BASE)
    body = r.json()["data"]

    trend = body["qa_trend"]
    assert len(trend) == 14
    # 最后一天（今天）应有 1 条
    assert trend[-1]["count"] == 1
    # 日期严格递增
    dates = [p["date"] for p in trend]
    assert dates == sorted(dates)
    # 问答总数 = 趋势和
    assert sum(p["count"] for p in trend) == 3


def test_dashboard_distributions(client):
    """文档状态分布（1..7 全枚举）+ 检索模式分布。"""
    _seed_dashboard_data(client)
    r = client.get(BASE)
    body = r.json()["data"]

    # 文档状态：status=6 一条、status=7 一条，其余 0
    status_map = {item["status"]: item["count"] for item in body["doc_status"]}
    assert set(status_map) == {1, 2, 3, 4, 5, 6, 7}
    assert status_map[6] == 1
    assert status_map[7] == 1

    # 检索模式：dense=1, hybrid=1
    mode_map = {item["mode"]: item["count"] for item in body["retrieval_modes"]}
    assert mode_map == {"dense": 1, "hybrid": 1}


def test_dashboard_recent_qa(client):
    """最近问答 Top N：按 created_at 倒序。"""
    _seed_dashboard_data(client)
    r = client.get(BASE)
    body = r.json()["data"]

    recent = body["recent_qa"]
    assert len(recent) == 3  # 仅 3 条，不足 Top 5 全返回
    # 最新在前（问题A 是 now，最新）
    assert recent[0]["question"] == "问题A"
    assert recent[0]["grounded"] is True


def test_dashboard_empty(client):
    """空库：计数全 0，趋势 14 天全 0，无异常。"""
    r = client.get(BASE)
    assert r.status_code == 200
    body = r.json()["data"]

    assert body["kb_count"] == 0
    assert body["doc_count"] == 0
    assert body["qa_count"] == 0
    assert body["total_cost"] == 0.0
    assert body["failed_doc_count"] == 0
    assert len(body["qa_trend"]) == 14
    assert all(p["count"] == 0 for p in body["qa_trend"])
    assert body["recent_qa"] == []
