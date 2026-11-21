"""LLM 客户端协议与数据契约（Plan 2 Task 16）。

对齐 OpenAI 兼容 /chat/completions 协议，与 embedding 客户端同构
（base_url + api_key + model 三字段）。流式走 SSE `data:` 行。
"""
from dataclasses import dataclass
from typing import Iterator, Protocol


class LLMError(Exception):
    """LLM 调用失败（重试耗尽 / 不可重试错误 / 畸形响应）；问答链路据此折叠。"""


@dataclass
class ChatMessage:
    """一条对话消息（role = system / user / assistant）。"""

    role: str
    content: str


@dataclass
class ChatResult:
    """非流式 chat 的完整结果。"""

    content: str
    tokens_in: int = 0
    tokens_out: int = 0


@dataclass
class StreamChunk:
    """流式 chat 的一个增量片段。

    tokens_in/tokens_out 只在 finish=True 的末帧有值（厂商通常在末帧回 usage）；
    客户端拿不到 usage 时保持 0，调用方需自行兜底估算成本。
    """

    delta: str
    finish: bool = False  # 最后一个片段（`[DONE]` 或 stream 结束）
    tokens_in: int = 0
    tokens_out: int = 0


class LLMClient(Protocol):
    def chat(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.3,
        max_tokens: int | None = None,
    ) -> ChatResult:
        """非流式：一次返回完整回答。"""
        ...

    def chat_stream(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.3,
        max_tokens: int | None = None,
    ) -> Iterator[StreamChunk]:
        """流式：逐片段 yield StreamChunk；最后一片 finish=True。"""
        ...
