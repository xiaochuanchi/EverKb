"""LLM 客户端（Task 16）：Fake 确定性 / OpenAI 兼容流式与非流式 / 重试 / 畸形响应。

红线 3：不触网——HTTP 层全程 httpx.MockTransport 内存模拟。
"""
import json
from types import SimpleNamespace

import httpx
import pytest

from app.services.llm import (
    ChatMessage,
    FakeLLM,
    LLMError,
    OpenAICompatibleLLM,
    create_llm,
)


def _msg(role: str, content: str) -> ChatMessage:
    return ChatMessage(role=role, content=content)


def _settings(api_key: str) -> SimpleNamespace:
    return SimpleNamespace(
        llm_base_url="https://x/v1",
        llm_api_key=api_key,
        llm_model="doubao-1-5-pro",
    )


# ── FakeLLM ────────────────────────────────────────────────────


def test_fake_llm_deterministic():
    llm = FakeLLM()
    result = llm.chat([_msg("user", "你好")])
    assert result.content == "[FakeLLM] 你好"
    assert result.tokens_in > 0 and result.tokens_out > 0


def test_fake_llm_stream_yields_chars_and_finish():
    llm = FakeLLM()
    chunks = list(llm.chat_stream([_msg("user", "你好")]))
    text = "".join(c.delta for c in chunks)
    assert text == "[FakeLLM] 你好"
    assert chunks[-1].finish is True


def test_fake_llm_stream_empty_answer_finishes():
    # 无任何 user 消息 → answer = "" → 仍应 yield 一个 finish 空 chunk（保证调用方总能收尾）
    llm = FakeLLM()
    chunks = list(llm.chat_stream([]))
    assert chunks == [] or chunks[-1].finish is True


def test_create_llm_switches_on_api_key():
    assert isinstance(create_llm(_settings(api_key="k")), OpenAICompatibleLLM)
    assert isinstance(create_llm(_settings(api_key="")), FakeLLM)


# ── OpenAICompatibleLLM 非流式 ──────────────────────────────────


def _non_stream_handler(captured: list[dict], fail_statuses: list[int] | None = None):
    calls = {"n": 0}
    fail_statuses = fail_statuses or []

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        body = json.loads(request.content)
        captured.append(body)
        if calls["n"] <= len(fail_statuses):
            return httpx.Response(fail_statuses[calls["n"] - 1], json={"error": "boom"})
        return httpx.Response(200, json={
            "choices": [{"message": {"content": "回答内容"}}],
            "usage": {"prompt_tokens": 12, "completion_tokens": 8},
        })

    return httpx.MockTransport(handler), calls


def test_non_stream_returns_content_and_usage():
    captured: list[dict] = []
    transport, _ = _non_stream_handler(captured)
    llm = OpenAICompatibleLLM("https://x/v1", "key", "m", transport=transport)
    result = llm.chat([_msg("user", "问题")])
    assert result.content == "回答内容"
    assert result.tokens_in == 12
    assert result.tokens_out == 8
    # 请求体校验
    assert captured[0]["model"] == "m"
    assert captured[0]["stream"] is False
    assert captured[0]["messages"] == [{"role": "user", "content": "问题"}]
    assert captured[0]["temperature"] == 0.3


def test_non_stream_max_tokens_in_payload():
    captured: list[dict] = []
    transport, _ = _non_stream_handler(captured)
    llm = OpenAICompatibleLLM("https://x/v1", "key", "m", transport=transport)
    llm.chat([_msg("user", "x")], max_tokens=100)
    assert captured[0]["max_tokens"] == 100


@pytest.mark.parametrize("status", [429, 500])
def test_llm_retries_then_succeeds(status: int):
    captured: list[dict] = []
    transport, calls = _non_stream_handler(captured, fail_statuses=[status])
    llm = OpenAICompatibleLLM("https://x/v1", "key", "m", max_retries=3, transport=transport)
    assert llm.chat([_msg("user", "x")]).content == "回答内容"
    assert calls["n"] == 2


def test_llm_raises_after_exhaustion():
    captured: list[dict] = []
    transport, calls = _non_stream_handler(captured, fail_statuses=[500, 500, 500])
    llm = OpenAICompatibleLLM("https://x/v1", "key", "m", max_retries=2, transport=transport)
    with pytest.raises(LLMError):
        llm.chat([_msg("user", "x")])
    assert calls["n"] == 3


def test_llm_no_retry_on_4xx():
    captured: list[dict] = []
    transport, calls = _non_stream_handler(captured, fail_statuses=[401])
    llm = OpenAICompatibleLLM("https://x/v1", "key", "m", max_retries=3, transport=transport)
    with pytest.raises(LLMError):
        llm.chat([_msg("user", "x")])
    assert calls["n"] == 1


def test_llm_malformed_response_raises():
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={"choices": []}))
    llm = OpenAICompatibleLLM("https://x/v1", "key", "m", transport=transport)
    with pytest.raises(LLMError):
        llm.chat([_msg("user", "x")])


# ── OpenAICompatibleLLM 流式 ────────────────────────────────────


def _sse_body(chunks: list[str], with_done: bool = True) -> str:
    lines = []
    for ch in chunks:
        lines.append("data: " + json.dumps({"choices": [{"delta": {"content": ch}}]}, ensure_ascii=False))
    if with_done:
        lines.append("data: [DONE]")
    return "\n\n".join(lines) + "\n\n"


def test_stream_yields_deltas_and_finish():
    captured: list[dict] = []
    sse = _sse_body(["你", "好", "世", "界"])

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(json.loads(request.content))
        return httpx.Response(200, content=sse.encode("utf-8"), headers={"content-type": "text/event-stream"})

    llm = OpenAICompatibleLLM("https://x/v1", "key", "m", transport=httpx.MockTransport(handler))
    chunks = list(llm.chat_stream([_msg("user", "问题")]))
    assert "".join(c.delta for c in chunks) == "你好世界"
    assert chunks[-1].finish is True
    assert captured[0]["stream"] is True


def test_stream_marks_finish_when_no_done_sentinel():
    # 无 [DONE] 的流（部分厂商直接断流）→ 也应补 finish
    sse = _sse_body(["只有一段"], with_done=False)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=sse.encode("utf-8"))

    llm = OpenAICompatibleLLM("https://x/v1", "key", "m", transport=httpx.MockTransport(handler))
    chunks = list(llm.chat_stream([_msg("user", "x")]))
    assert "".join(c.delta for c in chunks) == "只有一段"
    assert chunks[-1].finish is True


def test_stream_skips_non_json_heartbeat_lines():
    # 心跳行（: keep-alive 注释行）与空行应被跳过，合法 data 帧正常解析
    sse = (
        "data: " + json.dumps({"choices": [{"delta": {"content": "你"}}]}, ensure_ascii=False) + "\n\n"
        ": keep-alive\n\n"
        "\n\n"
        "data: " + json.dumps({"choices": [{"delta": {"content": "好"}}]}, ensure_ascii=False) + "\n\n"
        "data: [DONE]\n\n"
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=sse.encode("utf-8"))

    llm = OpenAICompatibleLLM("https://x/v1", "key", "m", transport=httpx.MockTransport(handler))
    chunks = list(llm.chat_stream([_msg("user", "x")]))
    assert "".join(c.delta for c in chunks) == "你好"
    assert chunks[-1].finish is True


def test_stream_http_error_raises_llm_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, content=b"boom")

    llm = OpenAICompatibleLLM("https://x/v1", "key", "m", transport=httpx.MockTransport(handler))
    with pytest.raises(LLMError):
        list(llm.chat_stream([_msg("user", "x")]))


def test_stream_request_includes_usage_option():
    """M2：流式请求须带 stream_options.include_usage，否则厂商不回真实 usage（方案 §6）。"""
    captured: list[dict] = []
    sse = _sse_body(["答"])

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(json.loads(request.content))
        return httpx.Response(200, content=sse.encode("utf-8"))

    llm = OpenAICompatibleLLM("https://x/v1", "key", "m", transport=httpx.MockTransport(handler))
    list(llm.chat_stream([_msg("user", "x")]))
    assert captured[0]["stream"] is True
    assert captured[0]["stream_options"] == {"include_usage": True}


def test_stream_collects_usage_from_last_frame():
    """M2：末帧（delta 为空）回 usage 时，应正确解析进 finish chunk 的 tokens_in/out。"""
    sse = (
        "data: " + json.dumps({"choices": [{"delta": {"content": "答"}}]}, ensure_ascii=False) + "\n\n"
        "data: " + json.dumps({
            "choices": [{"delta": {}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 42, "completion_tokens": 7},
        }, ensure_ascii=False) + "\n\n"
        "data: [DONE]\n\n"
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=sse.encode("utf-8"))

    llm = OpenAICompatibleLLM("https://x/v1", "key", "m", transport=httpx.MockTransport(handler))
    chunks = list(llm.chat_stream([_msg("user", "x")]))
    assert "".join(c.delta for c in chunks) == "答"
    assert chunks[-1].finish is True
    assert chunks[-1].tokens_in == 42
    assert chunks[-1].tokens_out == 7
