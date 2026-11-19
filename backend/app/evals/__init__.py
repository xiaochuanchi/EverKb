"""评测模块（二期 Task 27/28）：评测集构造 + 检索指标 + 消融编排。

三件套（计划文档 §4）：
- eval_set：EvalItem/EvalSet 数据契约 + 版本化落盘；
- synthesize：合成法（从 chunk 反向抽 query）；
- metrics：Recall@k / MRR / Hit@k；
- run_eval：三路消融（dense/sparse/hybrid）。
"""
from app.evals.eval_set import EvalItem, EvalSet, load_eval_set, now_iso, save_eval_set  # noqa: F401
from app.evals.metrics import evaluate, hit_rate, mrr, recall_at_k  # noqa: F401
from app.evals.run_eval import run_ablation  # noqa: F401
from app.evals.synthesize import build_eval_set, synthesize_queries  # noqa: F401

__all__ = [
    "EvalItem",
    "EvalSet",
    "build_eval_set",
    "evaluate",
    "hit_rate",
    "load_eval_set",
    "mrr",
    "now_iso",
    "recall_at_k",
    "run_ablation",
    "save_eval_set",
    "synthesize_queries",
]
