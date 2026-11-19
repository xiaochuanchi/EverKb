"""检索消融实验脚本（二期 Task 28 Step 3）：三路检索器跑评测集，产出指标报告。

手动执行（真实 Milvus + 评测库）：
    python scripts/run_ablation.py

三路（决策文档 §4.1）：
- dense：纯向量（Milvus COSINE）
- sparse：纯 BM25（内存倒排）
- hybrid：RRF 混合（向量 + BM25）

产出 docs/2026-11-19-检索评测报告.md：三路 Recall@k / MRR / Hit@k 对比表 + 结论。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.core.config import get_settings  # noqa: E402
from app.core.db import make_engine, make_session_factory  # noqa: E402
from app.evals import load_eval_set, run_ablation  # noqa: E402
from app.models import Chunk, Document, KnowledgeBase  # noqa: E402
from app.services.embedding import create_embedder  # noqa: E402
from app.services.vector import BM25Index, HybridRetriever, create_vector  # noqa: E402

EVAL_KB_NAME = "kb-eval-legal"
EVAL_SET_PATH = Path(__file__).resolve().parents[1] / "data" / "legal" / "eval_set.json"
REPORT_PATH = Path(__file__).resolve().parents[1] / "docs" / "2026-11-19-检索评测报告.md"

TOP_K = 5
OVERSAMPLE = 4


def _main() -> int:
    settings = get_settings()
    engine = make_engine(settings.mysql_url)
    session_factory = make_session_factory(engine)
    embedder = create_embedder(settings)
    vector = create_vector(settings)

    # 加载评测集 + 从评测库 chunk 建 BM25 索引
    eval_set = load_eval_set(EVAL_SET_PATH)
    print(f"评测集：{len(eval_set.items)} 条（v{eval_set.version}, seed={eval_set.seed}）")

    bm25 = BM25Index()
    kb_id = None
    with session_factory() as session:
        kb = session.query(KnowledgeBase).filter(KnowledgeBase.name == EVAL_KB_NAME).first()
        kb_id = kb.id
        chunks = session.query(Chunk).filter(Chunk.kb_id == kb_id).all()
        for c in chunks:
            bm25.add(c.id, c.content, doc_id=c.document_id, kb_id=c.kb_id, enabled=True)
        print(f"BM25 索引：{len(chunks)} chunk")

    retriever = HybridRetriever(vector, bm25)

    def _dense(query: str) -> list[int]:
        qv = embedder.embed([query])[0]
        return [h.chunk_id for h in vector.search(qv, [kb_id], top_k=TOP_K)]

    def _sparse(query: str) -> list[int]:
        return [h.chunk_id for h in bm25.search(query, [kb_id], top_k=TOP_K)]

    def _hybrid(query: str) -> list[int]:
        qv = embedder.embed([query])[0]
        return [h.chunk_id for h in retriever.search(
            query, qv, kb_ids=[kb_id], top_k=TOP_K, oversample=OVERSAMPLE,
        )]

    print("跑三路消融…")
    result = run_ablation(eval_set.items, _dense, _sparse, _hybrid, k=TOP_K)

    # 生成报告（chunk 数动态传入，避免切块参数调整后报告数字失真）
    _write_report(result, len(eval_set.items), TOP_K, n_chunks=len(chunks))
    print(f"报告已生成：{REPORT_PATH}")
    for name in ("dense", "sparse", "hybrid"):
        m = result[name]
        print(f"  {name:8s} recall@{TOP_K}={m['recall@k']:.3f}  mrr={m['mrr']:.3f}  hit@{TOP_K}={m['hit@k']:.3f}")
    return 0


def _write_report(result: dict, n_items: int, top_k: int, n_chunks: int) -> None:
    """落 Markdown 报告：对比表 + 结论。"""
    def _pct(x: float) -> str:
        return f"{x * 100:.1f}%"

    rows = []
    for name, label in (("dense", "纯向量"), ("sparse", "纯 BM25"), ("hybrid", "RRF 混合")):
        m = result[name]
        rows.append(
            f"| {label} | {_pct(m['recall@k'])} | {_pct(m['mrr'])} | {_pct(m['hit@k'])} |"
        )

    # 结论：比较三路，找出最优
    best = max(result, key=lambda k: result[k]["recall@k"])
    best_label = {"dense": "纯向量", "sparse": "纯 BM25", "hybrid": "RRF 混合"}[best]
    hybrid = result["hybrid"]
    dense = result["dense"]
    sparse = result["sparse"]

    if hybrid["recall@k"] >= dense["recall@k"] and hybrid["recall@k"] >= sparse["recall@k"]:
        verdict = (
            "RRF 混合检索在 Recall@k 上不劣于单路（且通常更稳），"
            "印证「关键词精确 + 语义召回互补」的价值——法条检索中近义表述、专有名词、"
            "交叉引用场景下，纯向量易漏关键词命中，纯 BM25 易漏语义改写，混合互补。"
        )
    else:
        verdict = (
            f"本轮 {best_label} 的 Recall@k 最优；混合检索未占优，"
            "可能因评测集规模（合成法 ground truth 偏乐观）或 k 值选择，需人工抽检修正后复评。"
        )

    content = f"""# 检索评测报告（二期 · 混合检索消融实验）

- 日期：2026-11-19
- 评测集：`data/legal/eval_set.json`（合成法，{n_items} 条，seed=42）
- 评测库：`kb-eval-legal`（12 部「网络安全与数据合规」法规，{n_chunks} chunk）
- 三路：纯向量（Milvus COSINE）/ 纯 BM25（jieba 分词）/ RRF 混合（k=60）

## 指标对比（top_k={top_k}）

| 检索方式 | Recall@{top_k} | MRR | Hit@{top_k} |
|---|---|---|---|
{chr(10).join(rows)}

## 结论

{verdict}

## 方法局限（如实说明）

- **合成法 ground truth 偏乐观**：`relevant_chunk_ids` 假设「query 应命中来源 chunk 自身」，
  但 LLM 白话改写后的 query 可能命中语义等价的其他 chunk，导致三路指标普遍偏高、
  区分度被压缩。已预留人工抽检 10% 入口修正。
- **评测集规模有限**：{n_chunks} chunk 抽样 {n_items} 条，消融实验的分辨率受限于法规包体量。
- **RRF 参数**：k=60（经典默认值），oversample=4，未做参数扫描。
"""
    REPORT_PATH.write_text(content, encoding="utf-8")


if __name__ == "__main__":
    sys.exit(_main())
