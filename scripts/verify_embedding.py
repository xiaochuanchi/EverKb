"""Embedding 真实连通性验证（排期 §3 / Plan 1 Task 8 Step 3）：DashScope 兼容模式。

手动执行：填好 .env 的 EMBEDDING_API_KEY 后 `python scripts/verify_embedding.py`。
打印 2 条文本的向量维度与余弦相似度——相近主题句与无关句相似度应明显拉开，
维度 == embedding_dim，即端点与配置可用。
"""
import sys
from pathlib import Path

# 脚本位于仓库根 scripts/，app 包在 backend/ 下：锚定后任意工作目录可执行
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.core.config import get_settings  # noqa: E402
from app.services.embedding import EmbeddingError, create_embedder  # noqa: E402


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(x * x for x in b) ** 0.5
    return dot / (na * nb) if na and nb else 0.0


def main() -> int:
    settings = get_settings()
    if not settings.embedding_api_key:
        print("缺少配置：EMBEDDING_API_KEY（填 .env 后重试）")
        return 1

    embedder = create_embedder(settings)
    texts = [
        "如何在本平台上传文档并构建知识库？",
        "今天天气不错，适合出去散步。",
    ]
    try:
        vecs = embedder.embed(texts)
    except EmbeddingError as e:
        print(f"embedding 调用失败：{e}")
        return 1

    for text, vec in zip(texts, vecs):
        print(f"dim={len(vec)}  text={text[:24]}")
    sim = _cosine(vecs[0], vecs[1])
    print(f"余弦相似度（KB 主题句 vs 无关闲聊句）：{sim:.4f}")
    if len(vecs[0]) != settings.embedding_dim:
        print(f"维度不符：期望 {settings.embedding_dim}，实际 {len(vecs[0])}")
        return 1
    print(f"verify_embedding OK（model={settings.embedding_model}, endpoint={settings.embedding_base_url}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
