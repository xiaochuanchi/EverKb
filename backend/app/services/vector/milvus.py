"""Milvus 向量客户端实现（pymilvus MilvusClient，Plan 1 Task 9）。

schema 按 Global Constraints：collection 名取 settings；HNSW(M=16,
efConstruction=200) COSINE；kb_id 为 partition key；chunk_text
VARCHAR(16384)；MySQL chunk.id 兼作 Milvus 主键（auto_id=False）。

set_doc_enabled = query 取回含 vector 的整行 → 翻 enabled → upsert。
"""
from pymilvus import DataType, MilvusClient

from app.services.vector.base import SearchHit, VectorRow

# 检索/查询时取回的业务字段（vector 仅 set_doc_enabled 需要单独 query）
_OUTPUT_FIELDS = ["doc_id", "kb_id", "chunk_text", "page_number"]
# pymilvus 默认 Bounded 一致性：写入后数秒读不可见，会踩空「写后立读」路径
# （set_doc_enabled 的 query 取回、清库后的 count 校验）；一期单体用 Strong 换读己之写
_CONSISTENCY = "Strong"


class MilvusVectorClient:
    def __init__(self, uri: str, collection_name: str, dim: int) -> None:
        self._client = MilvusClient(uri=uri)
        self._collection = collection_name
        self._dim = dim

    def ensure_collection(self) -> None:
        """幂等建 collection + HNSW 索引；已存在直接跳过。"""
        if self._client.has_collection(self._collection):
            return
        schema = MilvusClient.create_schema(auto_id=False, enable_dynamic_field=False)
        schema.add_field("id", DataType.INT64, is_primary=True)
        schema.add_field("vector", DataType.FLOAT_VECTOR, dim=self._dim)
        schema.add_field("chunk_text", DataType.VARCHAR, max_length=16384)
        schema.add_field("page_number", DataType.INT64, nullable=True)
        schema.add_field("doc_id", DataType.INT64)
        schema.add_field("kb_id", DataType.INT64, is_partition_key=True)
        schema.add_field("enabled", DataType.BOOL)
        index_params = MilvusClient.prepare_index_params()
        index_params.add_index(
            field_name="vector", index_type="HNSW", metric_type="COSINE",
            params={"M": 16, "efConstruction": 200},
        )
        self._client.create_collection(
            self._collection, schema=schema, index_params=index_params,
            consistency_level=_CONSISTENCY,
        )

    def insert(self, rows: list[VectorRow]) -> None:
        if not rows:
            return
        self._client.insert(self._collection, data=[self._to_entity(r) for r in rows])

    def search(
        self,
        query_vector: list[float],
        kb_ids: list[int],
        top_k: int = 5,
        threshold: float | None = None,
    ) -> list[SearchHit]:
        if not kb_ids:
            return []
        # COSINE 的 distance 即相似度（越大越近），partition key 过滤自动做分区裁剪
        filt = f"kb_id in {[int(k) for k in kb_ids]} and enabled == True"
        results = self._client.search(
            self._collection,
            data=[list(query_vector)],
            filter=filt,
            limit=top_k,
            output_fields=_OUTPUT_FIELDS,
            consistency_level=_CONSISTENCY,
        )
        hits: list[SearchHit] = []
        for row in results[0]:
            score = float(row["distance"])
            if threshold is not None and score < threshold:
                continue
            entity = row["entity"]
            hits.append(SearchHit(
                chunk_id=int(row["id"]),
                doc_id=int(entity["doc_id"]),
                kb_id=int(entity["kb_id"]),
                score=score,
                chunk_text=entity["chunk_text"],
                page_number=entity.get("page_number"),
            ))
        return hits

    def delete_by_doc(self, doc_id: int) -> None:
        self._client.delete(self._collection, filter=f"doc_id == {int(doc_id)}")

    def delete_by_ids(self, ids: list[int]) -> None:
        if not ids:
            return
        self._client.delete(self._collection, filter=f"id in {[int(i) for i in ids]}")

    def set_doc_enabled(self, doc_id: int, enabled: bool) -> None:
        rows = self._client.query(
            self._collection,
            filter=f"doc_id == {int(doc_id)}",
            output_fields=["id", "vector", *_OUTPUT_FIELDS],
            consistency_level=_CONSISTENCY,
        )
        if not rows:
            return
        for row in rows:
            row["enabled"] = enabled
        self._client.upsert(self._collection, data=rows)

    def count_by_doc(self, doc_id: int) -> int:
        res = self._client.query(
            self._collection,
            filter=f"doc_id == {int(doc_id)}",
            output_fields=["count(*)"],
            consistency_level=_CONSISTENCY,
        )
        return int(res[0]["count(*)"])

    @staticmethod
    def _to_entity(row: VectorRow) -> dict:
        """VectorRow → Milvus 行 dict；page_number 允许 None（nullable 字段）。"""
        return {
            "id": int(row.id),
            "vector": list(row.vector),
            "chunk_text": row.chunk_text,
            "page_number": row.page_number,
            "doc_id": int(row.doc_id),
            "kb_id": int(row.kb_id),
            "enabled": bool(row.enabled),
        }
