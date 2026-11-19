"""检索消融实验编排（二期 Task 28）：三路检索器各跑一遍评测集，产出指标对比。

三路（计划文档 §4.1）：
- dense：纯向量（COSINE）；
- sparse：纯 BM25（关键词）；
- hybrid：RRF 混合。

每路接收「query → 命中 chunk_id 列表」的函数，对评测集逐条跑分，
产出 {"dense": {...}, "sparse": {...}, "hybrid": {...}} 的指标字典。

纪律：指标计算确定（metrics 纯函数），同一评测集 + 同一检索器两次跑分一致。
"""
from __future__ import annotations

from collections.abc import Callable

from app.evals.metrics import evaluate


def run_ablation(
    eval_items,
    dense_fn: Callable[[str], list[int]],
    sparse_fn: Callable[[str], list[int]],
    hybrid_fn: Callable[[str], list[int]],
    *,
    k: int = 5,
) -> dict:
    """对三种检索器各跑一遍评测集，输出 Recall@k / MRR / Hit@k 对比。

    检索器函数入参为 query 字符串，返回命中 chunk_id 列表（有序）。
    eval_items 为 EvalItem 列表（含 query / relevant_chunk_ids）。
    """
    queries = [it.query for it in eval_items]
    relevant = [it.relevant_chunk_ids for it in eval_items]

    def _run(fn: Callable[[str], list[int]]) -> dict[str, float]:
        pairs = [(fn(q), rel) for q, rel in zip(queries, relevant)]
        return evaluate(pairs, k=k)

    return {
        "dense": _run(dense_fn),
        "sparse": _run(sparse_fn),
        "hybrid": _run(hybrid_fn),
    }
