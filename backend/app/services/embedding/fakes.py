"""FakeEmbedder：确定性假向量，测试双件套之一（架构约定：测试不触网）。

公式按计划钉死：第 i 维 = ((len(text)*31 + i) mod 97) / 97——相同文本恒等，
不同文本（长度不同）向量不同。
"""


class FakeEmbedder:
    def __init__(self, dim: int = 1024) -> None:
        self.dim = dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [
            [float((len(text) * 31 + i) % 97) / 97 for i in range(self.dim)]
            for text in texts
        ]
