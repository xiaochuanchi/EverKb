"""检索评测指标（二期 Task 28）：Recall@k / MRR / Hit@k，确定性、可复现。

指标语义（对检索器输出的命中 chunk_id 列表与 ground truth 相关集计算）：
- Recall@k：前 k 个命中里命中的相关 chunk 数 / 相关 chunk 总数；
- MRR：首个相关 chunk 的倒数排名（rank 从 1 起）的平均，未命中记 0；
- Hit@k：前 k 个命中里是否至少命中一个相关 chunk（0/1）。

纪律：同输入同输出（纯函数、无随机、无 IO），「两次跑分一致」红线。
"""
from __future__ import annotations


def recall_at_k(hits: list[int], relevant: list[int], *, k: int) -> float:
    """前 k 个命中里命中的相关 chunk 占比（相对相关集全量）。"""
    rel = set(relevant)
    if not rel:
        return 0.0
    top = set(hits[:k])
    return len(top & rel) / len(rel)


def mrr(hits: list[int], relevant: list[int]) -> float:
    """首个相关 chunk 的倒数排名；未命中记 0。rank 从 1 起。"""
    rel = set(relevant)
    for rank, cid in enumerate(hits, start=1):
        if cid in rel:
            return 1.0 / rank
    return 0.0


def hit_rate(hits: list[int], relevant: list[int], *, k: int) -> float:
    """前 k 个命中里是否命中至少一个相关 chunk。"""
    rel = set(relevant)
    if not rel:
        return 0.0
    return 1.0 if any(cid in rel for cid in hits[:k]) else 0.0


def evaluate(
    hits_by_query: list[tuple[list[int], list[int]]], *, k: int
) -> dict[str, float]:
    """对整份评测集聚合指标。

    入参：[(hits, relevant), ...] 每条样本的命中 chunk_id 与相关 chunk_id。
    返回：{"recall@k": float, "mrr": float, "hit@k": float}（均取均值）。
    """
    if not hits_by_query:
        return {"recall@k": 0.0, "mrr": 0.0, "hit@k": 0.0}
    n = len(hits_by_query)
    recall = sum(recall_at_k(h, r, k=k) for h, r in hits_by_query) / n
    mrr_val = sum(mrr(h, r) for h, r in hits_by_query) / n
    hit = sum(hit_rate(h, r, k=k) for h, r in hits_by_query) / n
    return {"recall@k": recall, "mrr": mrr_val, "hit@k": hit}
