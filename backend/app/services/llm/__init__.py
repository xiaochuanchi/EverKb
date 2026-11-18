"""LLM 服务包：LLMClient 协议 + OpenAI 兼容实现 + Fake（测试）。

create_llm 鸭子读取 llm_* 字段（Settings 与测试 SimpleNamespace 均可）：
配了 llm_api_key → OpenAI 兼容端点；否则 FakeLLM。
"""
from app.services.llm.base import ChatMessage, ChatResult, LLMError, LLMClient, StreamChunk  # noqa: F401
from app.services.llm.fakes import FakeLLM  # noqa: F401
from app.services.llm.openai_compatible import OpenAICompatibleLLM  # noqa: F401

__all__ = [
    "ChatMessage",
    "ChatResult",
    "FakeLLM",
    "LLMClient",
    "LLMError",
    "OpenAICompatibleLLM",
    "StreamChunk",
    "create_llm",
]


def create_llm(settings) -> LLMClient:
    """按 settings 构造 LLM 客户端：配了 llm_api_key 走真实端点，否则 Fake。"""
    if getattr(settings, "llm_api_key", ""):
        return OpenAICompatibleLLM(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key,
            model=settings.llm_model,
        )
    return FakeLLM()
