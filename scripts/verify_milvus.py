"""Milvus 真实连通性验证（排期 §3 / Plan 1 Task 9 Step 4）。

手动执行：`docker compose up -d` 后 `python scripts/verify_milvus.py`。
流程：ensure_collection → 插 3 条（doc_id=999999999 哨兵）→ search 断言
命中且排序正确 → delete_by_doc → count==0 → 打印 PASS。
"""
import math
import sys
from pathlib import Path

# 脚本位于仓库根 scripts/，app 包在 backend/ 下：锚定后任意工作目录可执行
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.core.config import get_settings  # noqa: E402
from app.services.vector import VectorRow, create_vector  # noqa: E402

VERIFY_DOC_ID = 999_999_999  # 验证哨兵 doc，结束后整删，不污染真实数据


def _main() -> int:
    settings = get_settings()
    client = create_vector(settings)
    dim = settings.embedding_dim

    # 1) 幂等建表（连续两次，第二次应无副作用）
    client.ensure_collection()
    client.ensure_collection()

    # 2) 插 3 条：vec_a 与查询向量同向（score=1），vec_b 夹角 45°，vec_c 正交（score≈0）
    query = [0.0] * dim
    query[0] = 1.0
    vec_a = [0.0] * dim
    vec_a[0] = 1.0
    vec_b = [0.0] * dim
    vec_b[0] = vec_b[1] = 1.0
    vec_c = [0.0] * dim
    vec_c[2] = 1.0
    rows = [
        VectorRow(id=1, vector=vec_a, chunk_text="同向 chunk", page_number=1,
                  doc_id=VERIFY_DOC_ID, kb_id=1, enabled=True),
        VectorRow(id=2, vector=vec_b, chunk_text="斜向 chunk", page_number=2,
                  doc_id=VERIFY_DOC_ID, kb_id=1, enabled=True),
        VectorRow(id=3, vector=vec_c, chunk_text="正交 chunk", page_number=None,
                  doc_id=VERIFY_DOC_ID, kb_id=1, enabled=True),
    ]
    client.insert(rows)

    try:
        # 3) search：top3 按分数降序；kb 过滤与阈值生效
        hits = client.search(query, kb_ids=[1], top_k=3)
        assert [h.chunk_id for h in hits] == [1, 2, 3], f"排序异常：{[h.chunk_id for h in hits]}"
        assert hits[0].score > 0.99 and hits[2].score < 0.01, \
            f"分数异常：{[h.score for h in hits]}"
        assert hits[2].page_number is None, "nullable page_number 未按 None 取回"
        filtered = client.search(query, kb_ids=[1], top_k=3, threshold=0.5)
        assert [h.chunk_id for h in filtered] == [1, 2], f"阈值过滤异常：{filtered}"
        assert client.search(query, kb_ids=[2], top_k=3) == [], "kb 过滤失效"
        print(f"search 命中：scores={[round(h.score, 4) for h in hits]}")

        # 4) set_doc_enabled：整文档停用后不可见，恢复后可见
        client.set_doc_enabled(VERIFY_DOC_ID, False)
        assert client.search(query, kb_ids=[1], top_k=3) == [], "停用后仍可命中"
        client.set_doc_enabled(VERIFY_DOC_ID, True)
        assert len(client.search(query, kb_ids=[1], top_k=3)) == 3, "恢复后未命中"

        # 5) delete_by_ids / delete_by_doc + count 清零
        client.delete_by_ids([3])
        assert client.count_by_doc(VERIFY_DOC_ID) == 2, "按 id 删除未生效"
        client.delete_by_doc(VERIFY_DOC_ID)
        assert client.count_by_doc(VERIFY_DOC_ID) == 0, "按 doc 删除后仍有残留"
    finally:
        client.delete_by_doc(VERIFY_DOC_ID)  # 中途断言失败也清哨兵数据

    print(f"PASS（uri={settings.milvus_uri}, collection={settings.collection_name}, dim={dim},"
          f" cos45≈{math.cos(math.pi / 4):.4f} 对照）")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
