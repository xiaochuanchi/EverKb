"""FakeVector：内存向量库，测试双件套之一（架构约定：测试不触网）。

按 Milvus COSINE 语义模拟：score = 余弦相似度，enabled 行才可被检索，
count 按存储行数计（含停用行，与真实 query 不带 enabled 过滤一致）。
"""
from app.services.vector.base import SearchHit, VectorRow


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(x * x for x in b) ** 0.5
    return dot / (na * nb) if na and nb else 0.0


class FakeVector:
    def __init__(self, dim: int = 1024) -> None:
        self.dim = dim
        self._rows: dict[int, VectorRow] = {}
        # 测试观察点：delete_by_ids 实际收到的 id（替换语义「精准清旧」断言用）
        self.deleted_ids: list[int] = []
        # 测试观察点（Task 11）：delete_by_doc / set_doc_enabled 实际收到的调用
        self.deleted_doc_ids: list[int] = []
        self.set_enabled_calls: list[tuple[int, bool]] = []

    def ensure_collection(self) -> None:
        pass  # 内存实现无表可建

    def insert(self, rows: list[VectorRow]) -> None:
        for row in rows:
            self._rows[row.id] = row  # 主键幂等，后写覆盖（同 Milvus upsert 语义）

    def search(
        self,
        query_vector: list[float],
        kb_ids: list[int],
        top_k: int = 5,
        threshold: float | None = None,
    ) -> list[SearchHit]:
        kb_set = set(kb_ids)
        scored = [
            (_cosine(query_vector, r.vector), r)
            for r in self._rows.values()
            if r.kb_id in kb_set and r.enabled
        ]
        scored.sort(key=lambda pair: pair[0], reverse=True)
        hits = []
        for score, r in scored[:top_k]:
            if threshold is not None and score < threshold:
                continue
            hits.append(SearchHit(
                chunk_id=r.id, doc_id=r.doc_id, kb_id=r.kb_id,
                score=score, chunk_text=r.chunk_text, page_number=r.page_number,
            ))
        return hits

    def delete_by_doc(self, doc_id: int) -> None:
        self.deleted_doc_ids.append(doc_id)
        self._rows = {rid: r for rid, r in self._rows.items() if r.doc_id != doc_id}

    def delete_by_ids(self, ids: list[int]) -> None:
        self.deleted_ids.extend(ids)
        for rid in ids:
            self._rows.pop(rid, None)

    def set_doc_enabled(self, doc_id: int, enabled: bool) -> None:
        self.set_enabled_calls.append((doc_id, enabled))
        for r in self._rows.values():
            if r.doc_id == doc_id:
                r.enabled = enabled

    def count_by_doc(self, doc_id: int) -> int:
        return sum(1 for r in self._rows.values() if r.doc_id == doc_id)
