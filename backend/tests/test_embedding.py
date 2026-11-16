"""Embedding 客户端（Task 8）：Fake 确定性 / OpenAI 兼容分批与 429、5xx 退避重试。

红线 3：不触网——HTTP 层全程 httpx.MockTransport 内存模拟。
"""
import json
from types import SimpleNamespace

import httpx
import pytest

from app.services.embedding import EmbeddingError, FakeEmbedder, OpenAIEmbedder, create_embedder


def _settings(api_key: str) -> SimpleNamespace:
    """create_embedder 按字段鸭子读取，不构造真 Settings（避免吃 .env 状态）。"""
    return SimpleNamespace(
        embedding_base_url="https://x/v1",
        embedding_api_key=api_key,
        embedding_model="text-embedding-v4",
        embedding_dim=1024,
        embedding_batch_size=10,
    )


def _mock_endpoint(captured: list[dict], fail_statuses: list[int] | None = None):
    """构造 MockTransport handler：请求体外捕到 captured；按序先失败后成功。

    成功响应的向量 = [len(text)] * 4，可据长度断言批次顺序正确映射回原位置。
    返回 (transport, calls)，calls["n"] 为请求总数。
    """
    calls = {"n": 0}
    fail_statuses = fail_statuses or []

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        body = json.loads(request.content)
        captured.append(body)
        if calls["n"] <= len(fail_statuses):
            return httpx.Response(fail_statuses[calls["n"] - 1], json={"error": "boom"})
        return httpx.Response(200, json={"data": [
            {"embedding": [float(len(t))] * 4, "index": i} for i, t in enumerate(body["input"])
        ]})

    return httpx.MockTransport(handler), calls


def test_fake_embedder_deterministic():
    emb = FakeEmbedder(dim=8)
    vecs = emb.embed(["你好世界", "你好世界", "别的"])
    assert len(vecs) == 3
    assert all(len(v) == 8 for v in vecs)
    assert vecs[0] == vecs[1]  # 相同文本恒等
    assert vecs[0] != vecs[2]
    assert vecs[0] == [float((4 * 31 + i) % 97) / 97 for i in range(8)]  # 公式按计划钉死


def test_create_embedder_switches_on_api_key():
    assert isinstance(create_embedder(_settings(api_key="k")), OpenAIEmbedder)
    assert isinstance(create_embedder(_settings(api_key="")), FakeEmbedder)


def test_openai_embedder_batches_requests():
    captured: list[dict] = []
    transport, _ = _mock_endpoint(captured)
    emb = OpenAIEmbedder("https://x/v1", "key", "text-embedding-v4", dim=4, batch_size=10, transport=transport)
    texts = [f"文本{i}" for i in range(12)]

    vecs = emb.embed(texts)

    assert len(vecs) == 12
    assert all(len(v) == 4 for v in vecs)
    assert len(captured) == 2                            # 12 条按 batch_size=10 → 恰 2 次请求
    assert all(len(r["input"]) <= 10 for r in captured)  # 每次请求体 ≤ batch_size
    assert captured[0]["input"] == texts[:10]
    assert captured[1]["input"] == texts[10:]
    assert captured[0]["model"] == "text-embedding-v4"
    assert captured[0]["dimensions"] == 4
    assert vecs[0] == [3.0] * 4                          # 「文本0」3 字符
    assert vecs[10] == [4.0] * 4                         # 「文本10」4 字符——批次结果顺序映射回原位置


@pytest.mark.parametrize("status", [429, 500])
def test_openai_embedder_retries_then_succeeds(status: int):
    captured: list[dict] = []
    transport, calls = _mock_endpoint(captured, fail_statuses=[status])
    emb = OpenAIEmbedder("https://x/v1", "key", "m", dim=4, max_retries=3, transport=transport)

    vecs = emb.embed(["一条"])

    assert vecs == [[2.0] * 4]  # 「一条」2 字符
    assert calls["n"] == 2      # 首次失败 + 重试成功


def test_openai_embedder_raises_after_exhaustion():
    captured: list[dict] = []
    transport, calls = _mock_endpoint(captured, fail_statuses=[500, 500, 500])
    emb = OpenAIEmbedder("https://x/v1", "key", "m", dim=4, max_retries=2, transport=transport)

    with pytest.raises(EmbeddingError):
        emb.embed(["一条"])

    assert calls["n"] == 3  # 首次 + max_retries 次；退避后仍失败则抛 EmbeddingError


def test_openai_embedder_no_retry_on_4xx():
    captured: list[dict] = []
    transport, calls = _mock_endpoint(captured, fail_statuses=[401])
    emb = OpenAIEmbedder("https://x/v1", "key", "m", dim=4, max_retries=3, transport=transport)

    with pytest.raises(EmbeddingError):
        emb.embed(["一条"])

    assert calls["n"] == 1  # 401 类不可重试错误立即抛出
