"""OpenAI 兼容 LLM 客户端：POST {base_url}/chat/completions，流式 + 非流式。

预置端点为火山方舟豆包（OpenAI 兼容）。transport 参数仅测试注入用
（httpx.MockTransport），生产路径不传。

流式解析：`stream=True` 时响应为 SSE（text/event-stream），逐行 `data:` 分帧，
`data: [DONE]` 收尾；content 增量取自 choices[0].delta.content，
usage 取自最后一个带 usage 的帧（部分厂商在末帧回 usage）。
"""
import time

import httpx

from app.services.llm.base import ChatMessage, ChatResult, LLMError, StreamChunk

# 429 限流与 5xx 服务端错误可退避重试；其余 4xx（鉴权/参数）立即失败
_RETRY_STATUSES = {429, 500, 502, 503, 504}
_BACKOFF_BASE_SEC = 0.5
_REQUEST_TIMEOUT_SEC = 60  # 生成类请求允许更长的首字等待；流式由 stream 读取控制


class OpenAICompatibleLLM:
    """LLMClient 的 OpenAI 兼容实现；任何调用失败折叠为 LLMError，不向上抛裸异常。"""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        *,
        timeout: float = _REQUEST_TIMEOUT_SEC,
        max_retries: int = 2,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.max_retries = max_retries
        self.transport = transport

    # ── 公共入口 ────────────────────────────────────────────────

    def chat(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.3,
        max_tokens: int | None = None,
    ) -> ChatResult:
        payload = self._payload(messages, temperature, max_tokens, stream=False)
        resp = self._post_with_retry(payload)
        return self._parse_non_stream(resp)

    def chat_stream(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.3,
        max_tokens: int | None = None,
    ):
        payload = self._payload(messages, temperature, max_tokens, stream=True)
        # 流式不重试：一旦开始返回片段就无法安全重放；失败向上抛 LLMError
        try:
            with httpx.Client(transport=self.transport, timeout=self.timeout) as client:
                with client.stream(
                    "POST",
                    f"{self.base_url}/chat/completions",
                    json=payload,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                ) as resp:
                    if resp.status_code != 200:
                        body = resp.read().decode("utf-8", errors="replace")
                        raise LLMError(f"llm 请求失败：HTTP {resp.status_code} {body[:200]}")
                    yield from self._parse_stream(resp)
        except LLMError:
            raise
        except httpx.HTTPError as e:
            raise LLMError(f"llm 网络失败：{type(e).__name__}: {e}") from e

    # ── 内部 ────────────────────────────────────────────────────

    def _payload(
        self, messages: list[ChatMessage], temperature: float, max_tokens: int | None, stream: bool
    ) -> dict:
        payload: dict = {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
            "stream": stream,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        # 流式请求显式要求末帧回 usage（OpenAI 兼容协议 stream_options.include_usage），
        # 否则厂商不回真实 token 数、只能按字符估算，中文场景成本高估 1.5~2 倍（方案 §6）
        if stream:
            payload["stream_options"] = {"include_usage": True}
        return payload

    def _post_with_retry(self, payload: dict) -> httpx.Response:
        attempt = 0
        with httpx.Client(transport=self.transport, timeout=self.timeout) as client:
            while True:
                try:
                    resp = client.post(
                        f"{self.base_url}/chat/completions",
                        json=payload,
                        headers={"Authorization": f"Bearer {self.api_key}"},
                    )
                except httpx.HTTPError as e:
                    if self._backoff(attempt):
                        attempt += 1
                        continue
                    raise LLMError(f"llm 网络失败：{type(e).__name__}: {e}") from e
                if resp.status_code == 200:
                    return resp
                if resp.status_code in _RETRY_STATUSES and self._backoff(attempt):
                    attempt += 1
                    continue
                raise LLMError(f"llm 请求失败：HTTP {resp.status_code} {resp.text[:200]}")

    def _backoff(self, attempt: int) -> bool:
        if attempt < self.max_retries:
            time.sleep(_BACKOFF_BASE_SEC * (2 ** attempt))
            return True
        return False

    # ── 解析 ────────────────────────────────────────────────────

    def _parse_non_stream(self, resp: httpx.Response) -> ChatResult:
        try:
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            usage = data.get("usage", {}) or {}
            return ChatResult(
                content=content or "",
                tokens_in=int(usage.get("prompt_tokens") or 0),
                tokens_out=int(usage.get("completion_tokens") or 0),
            )
        except (KeyError, IndexError, TypeError, ValueError) as e:
            raise LLMError(f"llm 响应格式非法：{type(e).__name__}: {e}") from e

    def _parse_stream(self, resp: httpx.Response):
        finished = False
        tokens_in = 0
        tokens_out = 0
        for raw_line in resp.iter_lines():
            line = raw_line.strip()
            if not line or not line.startswith("data:"):
                continue
            payload = line[len("data:"):].strip()
            if payload == "[DONE]":
                finished = True
                break
            try:
                data = httpx.Response(200, content=payload.encode("utf-8")).json()
            except (ValueError, TypeError):
                # 个别厂商的 keep-alive 或非 JSON 心跳行，跳过
                continue
            # 部分厂商在末帧（delta 为空）回 usage，必须收集才能按 token 计费
            usage = data.get("usage")
            if isinstance(usage, dict):
                try:
                    tokens_in = int(usage.get("prompt_tokens") or tokens_in)
                    tokens_out = int(usage.get("completion_tokens") or tokens_out)
                except (TypeError, ValueError):
                    pass
            delta = self._extract_delta(data)
            if delta:
                yield StreamChunk(delta=delta)
        # 统一在末帧带 usage 收尾：[DONE] 正常结束与流意外中断共用同一出口
        yield StreamChunk(delta="", finish=True, tokens_in=tokens_in, tokens_out=tokens_out)

    @staticmethod
    def _extract_delta(data: dict) -> str:
        try:
            delta = data["choices"][0].get("delta", {}) or {}
            return delta.get("content") or ""
        except (KeyError, IndexError, TypeError):
            return ""
