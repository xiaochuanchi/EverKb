"""Embedder 协议与异常（Plan 1 Task 8）。"""
from typing import Protocol


class EmbeddingError(Exception):
    """embedding 调用失败（重试耗尽或不可重试错误）；管线据此将文档置为失败态。"""


class Embedder(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]:
        """批量向量化；返回向量维度 = embedding_dim，顺序与输入一致。"""
        ...
