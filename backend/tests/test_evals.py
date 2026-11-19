"""评测模块测试（Task 27/28）：指标正确性 + 评测集版本化 + 合成契约。

红线 3：测试不触网——合成用 FakeLLM 锁契约，指标纯函数确定性断言。
"""
import json

import pytest

from app.evals import (
    EvalItem,
    EvalSet,
    build_eval_set,
    evaluate,
    hit_rate,
    load_eval_set,
    mrr,
    recall_at_k,
    run_ablation,
    save_eval_set,
    synthesize_queries,
)
from app.services.llm import FakeLLM


# ── 指标 ──────────────────────────────────────────────────────


def test_recall_at_k_exact():
    hits = [10, 20, 30, 40, 50]
    relevant = [30, 99]  # 相关集含 30（命中）与 99（未命中）
    assert recall_at_k(hits, relevant, k=3) == 0.5  # 前 3 命中 30，相关集 2 个 → 1/2
    assert recall_at_k(hits, relevant, k=1) == 0.0  # 前 1 只有 10，未命中相关
    assert recall_at_k([], [], k=5) == 0.0


def test_mrr_uses_first_relevant_rank():
    hits = [10, 20, 30]
    assert mrr(hits, [20]) == 0.5  # 20 排第 2 → 1/2
    assert mrr(hits, [10]) == 1.0  # 10 排第 1 → 1/1
    assert mrr(hits, [99]) == 0.0  # 未命中 → 0
    assert mrr([], [1]) == 0.0


def test_hit_rate():
    hits = [10, 20, 30]
    assert hit_rate(hits, [20], k=2) == 1.0
    assert hit_rate(hits, [20], k=1) == 0.0  # 前 1 未命中 20
    assert hit_rate(hits, [99], k=5) == 0.0
    assert hit_rate(hits, [], k=5) == 0.0


def test_metrics_deterministic():
    """同一输入两次计算指标完全一致（可复现红线）。"""
    pairs = [([1, 2, 3], [2]), ([4, 5], [4]), ([], [1])]
    a = evaluate(pairs, k=5)
    b = evaluate(pairs, k=5)
    assert a == b
    # 精确值断言：recall = (1/1 + 1/1 + 0)/3 = 2/3；mrr = (0.5 + 1 + 0)/3 = 0.5
    assert a["recall@k"] == pytest.approx(2 / 3)
    assert a["mrr"] == pytest.approx(0.5)
    assert a["hit@k"] == pytest.approx(2 / 3)


# ── 评测集版本化 ──────────────────────────────────────────────


def test_evalset_load_and_version(tmp_path):
    items = [EvalItem(query="数据安全如何分级", relevant_chunk_ids=[1, 2], doc_name="数据安全法")]
    es = EvalSet(version=1, seed=42, created_at="2026-11-19T00:00:00+00:00", items=items)
    path = tmp_path / "eval_set.json"
    save_eval_set(es, path)
    loaded = load_eval_set(path)
    assert loaded.version == 1
    assert loaded.seed == 42
    assert loaded.created_at == "2026-11-19T00:00:00+00:00"
    assert len(loaded.items) == 1
    it = loaded.items[0]
    assert it.query == "数据安全如何分级"
    assert it.relevant_chunk_ids == [1, 2]
    assert it.doc_name == "数据安全法"
    # 落盘为可读 JSON，含版本字段
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["version"] == 1 and "items" in raw


def test_evalset_roundtrip_preserves_unicode(tmp_path):
    items = [EvalItem(query="个人信息保护法第几条？", relevant_chunk_ids=[7], doc_name="个保法")]
    es = EvalSet(version=2, seed=1, created_at="x", items=items)
    save_eval_set(es, tmp_path / "e.json")
    loaded = load_eval_set(tmp_path / "e.json")
    assert loaded.items[0].query == "个人信息保护法第几条？"


# ── 合成契约（FakeLLM）────────────────────────────────────────


def test_synthesize_queries_returns_n_lines():
    llm = FakeLLM()
    queries = synthesize_queries("数据安全法第一条", llm, n=3)
    assert len(queries) == 3


def test_synthesize_strips_numbering():
    """FakeLLM 回显带编号的前缀时，应剥掉编号。"""
    class _NumberingLLM(FakeLLM):
        def _answer(self, messages):
            return "1. 数据安全怎么分级？\n2、个人信息如何保护？\n3) 密码法是什么？"

    llm = _NumberingLLM()
    queries = synthesize_queries("某条文", llm, n=3)
    assert queries == ["数据安全怎么分级？", "个人信息如何保护？", "密码法是什么？"]


def test_build_eval_set_reproducible():
    """同 seed 两次抽样结果一致（可复现）；每 chunk 抽 per_chunk 个 query。"""
    llm = FakeLLM()
    chunks = [(i, f"条文内容 {i}", f"法规 {i}") for i in range(10)]
    a = build_eval_set(chunks, llm, sample_size=5, per_chunk=2, seed=42)
    b = build_eval_set(chunks, llm, sample_size=5, per_chunk=2, seed=42)
    assert [it.query for it in a] == [it.query for it in b]
    assert len(a) == 10  # 5 个 chunk × 2 query
    # 每个 item 的 relevant_chunk_ids = 抽中的那个 chunk id
    for it in a:
        assert len(it.relevant_chunk_ids) == 1


def test_build_eval_set_sample_size_capped():
    """sample_size 超过 chunk 总数时，只抽到 chunk 总数。"""
    llm = FakeLLM()
    chunks = [(1, "a", "doc"), (2, "b", "doc")]
    items = build_eval_set(chunks, llm, sample_size=100, per_chunk=1, seed=1)
    assert len(items) == 2


# ── 消融编排 ──────────────────────────────────────────────────


def test_run_ablation_returns_three_way_metrics():
    items = [
        EvalItem(query="q1", relevant_chunk_ids=[1], doc_name="d"),
        EvalItem(query="q2", relevant_chunk_ids=[2], doc_name="d"),
    ]
    dense = lambda q: [1, 2]  # noqa: E731
    sparse = lambda q: [2, 1]  # noqa: E731
    hybrid = lambda q: [1, 2]  # noqa: E731
    result = run_ablation(items, dense, sparse, hybrid, k=5)
    assert set(result.keys()) == {"dense", "sparse", "hybrid"}
    for name in ("dense", "sparse", "hybrid"):
        assert set(result[name].keys()) == {"recall@k", "mrr", "hit@k"}
    # 三路都能命中相关集（recall@k=1.0）
    assert result["dense"]["recall@k"] == pytest.approx(1.0)
    assert result["sparse"]["recall@k"] == pytest.approx(1.0)
    assert result["hybrid"]["recall@k"] == pytest.approx(1.0)
