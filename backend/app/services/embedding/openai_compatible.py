"""OpenAI 兼容 embeddings 客户端：POST {base_url}/embeddings，自动分批 + 429/5xx 退避重试。

预置端点为 DashScope 兼容模式（text-embedding-v4）。transport 参数仅测试注入用
（httpx.MockTransport），生产路径不传。请求携带 dimensions=dim（text-embedding-v4
按此返回指定维度）。
"""
import time

import httpx

from app.services.embedding.base import EmbeddingError

# 429 限流与 5xx 服务端错误可退避重试；其余 4xx（鉴权/参数）立即失败
_RETRY_STATUSES = {429, 500, 502, 503, 504}
_BACKOFF_BASE_SEC = 0.5  # 指数退避：0.5s, 1s, 2s, ...
_REQUEST_TIMEOUT_SEC = 30


class OpenAIEmbedder:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        dim: int,
        batch_size: int = 10,
        max_retries: int = 3,
        transport: httpx.BaseTransport | None = None,  # 测试注入 MockTransport 用
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.dim = dim
        self.batch_size = batch_size
        self.max_retries = max_retries
        self.transport = transport

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self.batch_size):
            batch = texts[start:start + self.batch_size]
            vectors.extend(self._embed_batch(batch))
        return vectors

    def _embed_batch(self, batch: list[str]) -> list[list[float]]:
        payload = {"model": self.model, "input": batch, "dimensions": self.dim}
        attempt = 0
        while True:
            with httpx.Client(transport=self.transport, timeout=_REQUEST_TIMEOUT_SEC) as client:
                resp = client.post(
                    f"{self.base_url}/embeddings",
                    json=payload,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                )
            if resp.status_code == 200:
                return self._parse(resp, len(batch))
            if resp.status_code in _RETRY_STATUSES and attempt < self.max_retries:
                time.sleep(_BACKOFF_BASE_SEC * (2 ** attempt))
                attempt += 1
                continue
            raise EmbeddingError(f"embedding 请求失败：HTTP {resp.status_code} {resp.text[:200]}")

    def _parse(self, resp: httpx.Response, batch_len: int) -> list[list[float]]:
        data = sorted(resp.json()["data"], key=lambda item: item["index"])
        if len(data) != batch_len:
            raise EmbeddingError(f"embedding 返回条数不符：要 {batch_len} 条，得 {len(data)} 条")
        vectors = [item["embedding"] for item in data]
        bad = next((len(v) for v in vectors if len(v) != self.dim), None)
        if bad is not None:
            raise EmbeddingError(f"embedding 维度不符：期望 {self.dim}，实际 {bad}")
        return vectors
