"""Trace 查看 API（Task 22）。挂载 /api/v1/admin/traces。

锁定点：span 树成树（parent_span_id）、聚合返回最慢 Top N + 各 span_type P95。
"""
from datetime import datetime, timedelta

from app.models import QaRecord, TraceSpan

BASE = "/api/v1/admin/traces"


def _seed_trace(client, *, trace_id, n=4) -> list[TraceSpan]:
    """造一条含 n 个 span 的链（parent 依次指向上一 span）。"""
    session = client.app.state.session_factory()
    spans = []
    parent_id = None
    base = datetime(2026, 1, 1, 12, 0, 0)
    for i in range(n):
        span = TraceSpan(
            trace_id=trace_id,
            parent_span_id=parent_id,
            name=f"span{i}",
            span_type=["embedding", "retrieval", "db", "llm"][i % 4],
            start_time=base + timedelta(milliseconds=i * 10),
            end_time=base + timedelta(milliseconds=i * 10 + 100 + i * 50),
            latency_ms=100 + i * 50,
            gen_ai_usage_tokens_in=10,
            gen_ai_usage_tokens_out=20,
        )
        session.add(span)
        session.flush()
        parent_id = span.id
        spans.append(span)
    session.commit()
    for s in spans:
        session.refresh(s)
    session.close()
    return spans


def _seed_record(client, *, app_id=1) -> QaRecord:
    session = client.app.state.session_factory()
    rec = QaRecord(app_id=app_id, user_key="u", question="q", answer="a", grounded=True)
    session.add(rec)
    session.commit()
    session.refresh(rec)
    session.close()
    return rec


def test_trace_span_tree(client):
    """span 按 parent_span_id 成树。"""
    rec = _seed_record(client)
    _seed_trace(client, trace_id=rec.id, n=4)

    r = client.get(f"{BASE}/{rec.id}")
    assert r.status_code == 200
    body = r.json()["data"]
    assert body["record_id"] == rec.id
    spans = body["spans"]
    assert len(spans) == 1  # 单链 → 一个根
    root = spans[0]
    assert root["parent_span_id"] is None
    # 逐层下钻 children
    node = root
    depth = 0
    while node["children"]:
        node = node["children"][0]
        depth += 1
    assert depth == 3  # 4 span 链，根下有 3 层


def test_trace_404(client):
    assert client.get(f"{BASE}/99999").status_code == 404


def test_trace_aggregate(client):
    """聚合：最慢 Top N + 各 span_type P95。"""
    rec1 = _seed_record(client)
    rec2 = _seed_record(client)
    _seed_trace(client, trace_id=rec1.id, n=4)
    _seed_trace(client, trace_id=rec2.id, n=4)

    r = client.get(f"{BASE}/aggregate")
    assert r.status_code == 200
    body = r.json()["data"]
    # 最慢 Top N（共 8 个 span）
    assert len(body["slowest"]) >= 1
    # 各 span_type 聚合
    types = {item["span_type"] for item in body["by_type"]}
    assert types == {"embedding", "retrieval", "db", "llm"}
    for item in body["by_type"]:
        assert item["count"] == 2  # 两个 trace 各一个
        assert item["p95_latency_ms"] is not None
