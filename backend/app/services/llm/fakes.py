"""FakeLLM：测试双件套之一（架构约定：测试不触网）。

确定性返回：按最后一条 user 消息内容回显一个固定回答，流式按字符切分 yield，
供问答链路 / SSE 端点测试注入，不依赖真实 LLM。
"""
from app.services.llm.base import ChatMessage, ChatResult, StreamChunk


class FakeLLM:
    """确定性 LLM：回答 = f"[FakeLLM] {最后一条 user 消息}"。

    tokens 按简单启发式估算（中文按字数、英文按空格分词），仅测试断言用。
    """

    def __init__(self, prefix: str = "[FakeLLM]") -> None:
        self.prefix = prefix

    def _answer(self, messages: list[ChatMessage]) -> str:
        last_user = next((m.content for m in reversed(messages) if m.role == "user"), "")
        return f"{self.prefix} {last_user}"

    def chat(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.3,
        max_tokens: int | None = None,
    ) -> ChatResult:
        answer = self._answer(messages)
        return ChatResult(content=answer, tokens_in=10, tokens_out=len(answer))

    def chat_stream(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.3,
        max_tokens: int | None = None,
    ):
        answer = self._answer(messages)
        for i, ch in enumerate(answer):
            yield StreamChunk(delta=ch, finish=(i == len(answer) - 1))
        if not answer:
            yield StreamChunk(delta="", finish=True)
