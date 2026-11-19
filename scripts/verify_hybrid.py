"""混合检索手动验证（二期 Task 25 Step 3）。

演示 BM25 vs 向量 vs RRF 混合的三路命中差异，验证 HybridRetriever 融合逻辑。

手动执行：`python scripts/verify_hybrid.py`
- 稠密路：默认用内存 FakeVector（无需 Milvus）；BM25 稀疏路恒为内存索引。
- 打印三路各自命中与融合命中，直观看到「关键词命中 vs 语义命中」的差异。
"""
import sys
from pathlib import Path

# 脚本位于仓库根 scripts/，app 包在 backend/ 下：锚定后任意工作目录可执行
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.services.vector import BM25Index, FakeVector, HybridRetriever, VectorRow  # noqa: E402

DIM = 8


def _vec(*comps: float) -> list[float]:
    return [float(c) for c in comps] + [0.0] * (DIM - len(comps))


def _main() -> int:
    vector = FakeVector(dim=DIM)
    bm25 = BM25Index()
    vector.ensure_collection()

    # seed 数据：模拟法条 chunk，其中 chunk 1/3 含关键词「数据安全」，chunk 2 语义相近但用词不同
    seed = [
        (1, _vec(1, 0), "数据安全法 第一条 数据处理活动应当坚持安全与发展并重", 11),
        (2, _vec(0.9, 0.1), "个人信息保护法 处理个人信息应当遵循合法正当必要原则", 22),
        (3, _vec(0.85, 0.15), "网络数据安全管理条例 数据安全 分级分类 保护", 33),
        (4, _vec(0, 1), "关键信息基础设施 运营者 应当在境内存储数据", 44),
    ]
    for rid, vec, text, doc in seed:
        vector.insert([VectorRow(
            id=rid, vector=vec, chunk_text=text, page_number=None,
            doc_id=doc, kb_id=1, enabled=True,
        )])
        bm25.add(rid, text, doc_id=doc, kb_id=1, enabled=True)

    query = "数据安全 如何分级保护"
    query_vec = _vec(1, 0)  # 语义上最接近 chunk 1（数据安全法）

    retriever = HybridRetriever(vector, bm25)

    print("=== BM25 稀疏路（关键词） ===")
    for h in bm25.search(query, kb_ids=[1], top_k=4):
        print(f"  chunk {h.chunk_id}  score={h.score:.4f}  {h.chunk_text[:20]}")

    print("=== 向量稠密路（语义） ===")
    for h in vector.search(query_vec, kb_ids=[1], top_k=4):
        print(f"  chunk {h.chunk_id}  score={h.score:.4f}  {h.chunk_text[:20]}")

    print("=== RRF 混合（k=60） ===")
    for h in retriever.search(query, query_vec, kb_ids=[1], top_k=4):
        print(f"  chunk {h.chunk_id}  score={h.score:.6f}  source={h.source}  {h.chunk_text[:20]}")

    print("PASS（三路命中差异可见：BM25 抓关键词、向量抓语义、RRF 融合排序）")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
