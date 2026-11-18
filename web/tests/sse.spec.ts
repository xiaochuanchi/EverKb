import { describe, expect, it, vi } from "vitest";

import { parseSseBuffer, streamChat } from "@/chat-kit/sse";

/**
 * SSE 客户端单测（F3 Task 31）。
 * 出网红线：用 fake fetch 注入 ReadableStream，全程进程内，零真实请求。
 */

describe("parseSseBuffer：SSE 帧解析", () => {
  it("解析单个完整帧（delta）", () => {
    const { events, remainder } = parseSseBuffer('data: {"delta":"你好"}\n\n');
    expect(events).toEqual([{ delta: "你好" }]);
    expect(remainder).toBe("");
  });

  it("解析收尾帧（grounded + citations）", () => {
    const frame =
      'data: {"grounded":true,"citations":[{"doc_name":"a.md","doc_id":1,"chunk_id":2,"page_number":null,"snippet":"s","score":0.9,"source_url":null}]}\n\n';
    const { events } = parseSseBuffer(frame);
    expect(events).toHaveLength(1);
    expect(events[0]).toMatchObject({ grounded: true });
  });

  it("跨 chunk 缓冲：不完整帧保留在 remainder，后续补齐再解析", () => {
    const first = parseSseBuffer('data: {"delta":"你');
    expect(first.events).toHaveLength(0);
    expect(first.remainder).toBe('data: {"delta":"你');

    const second = parseSseBuffer(first.remainder + '好"}\n\n');
    expect(second.events).toEqual([{ delta: "你好" }]);
    expect(second.remainder).toBe("");
  });

  it("忽略心跳/注释行（非 JSON 的 data 行）", () => {
    const { events } = parseSseBuffer("data: 心跳\n\ndata: {\"delta\":\"x\"}\n\n");
    expect(events).toEqual([{ delta: "x" }]);
  });

  it("多个帧一次性解析", () => {
    const buf = 'data: {"delta":"a"}\n\ndata: {"delta":"b"}\n\ndata: {"grounded":false,"citations":[]}\n\n';
    const { events, remainder } = parseSseBuffer(buf);
    expect(events).toHaveLength(3);
    expect(remainder).toBe("");
    expect(events[0]).toEqual({ delta: "a" });
    expect(events[2]).toEqual({ grounded: false, citations: [] });
  });
});

/** 用字符串分片构造一个 fake ReadableStream 响应 */
function fakeStreamResponse(chunks: string[]): Response {
  const encoder = new TextEncoder();
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const c of chunks) {
        controller.enqueue(encoder.encode(c));
      }
      controller.close();
    },
  });
  return {
    ok: true,
    status: 200,
    body: stream,
  } as unknown as Response;
}

function makeFakeFetch(chunks: string[]): typeof fetch {
  return (async () => fakeStreamResponse(chunks)) as unknown as typeof fetch;
}

describe("streamChat：流式问答客户端", () => {
  it("逐帧回调 delta，收尾回调 onDone", async () => {
    const onDelta = vi.fn();
    const onDone = vi.fn();
    const onError = vi.fn();

    const chunks = [
      'data: {"delta":"你"}\n\n',
      'data: {"delta":"好"}\n\n',
      'data: {"grounded":true,"citations":[]}\n\n',
    ];

    const handle = streamChat(
      "/api/v1/apps/1/chat",
      "sk-test",
      { question: "hi", user_key: "" },
      { onDelta, onDone, onError },
      makeFakeFetch(chunks),
    );

    // 等待流处理完成
    await vi.waitFor(() => expect(onDone).toHaveBeenCalled());
    expect(onDelta.mock.calls.map((c) => c[0])).toEqual(["你", "好"]);
    expect(onDone).toHaveBeenCalledWith({ grounded: true, citations: [] });
    expect(onError).not.toHaveBeenCalled();
    expect(handle.abort).toBeTypeOf("function");
  });

  it("跨 chunk 拆分的 delta 也能正确拼接", async () => {
    const onDelta = vi.fn();
    const onDone = vi.fn();

    // 故意把一帧拆到两个 chunk 里
    const chunks = [
      'data: {"delta":"你',
      '好"}\n\ndata: {"grounded":false,"citations":[]}\n\n',
    ];

    streamChat(
      "/api/v1/apps/1/chat",
      "sk-test",
      { question: "hi", user_key: "" },
      { onDelta, onDone, onError: vi.fn() },
      makeFakeFetch(chunks),
    );

    await vi.waitFor(() => expect(onDone).toHaveBeenCalled());
    expect(onDelta.mock.calls.map((c) => c[0])).toEqual(["你好"]);
  });

  it("非 2xx 响应回调 onError", async () => {
    const onError = vi.fn();
    const fakeFetch = (async () =>
      ({
        ok: false,
        status: 401,
        body: null,
      }) as unknown as Response) as unknown as typeof fetch;

    streamChat(
      "/api/v1/apps/1/chat",
      "bad-key",
      { question: "hi", user_key: "" },
      { onDelta: vi.fn(), onDone: vi.fn(), onError },
      fakeFetch,
    );

    await vi.waitFor(() => expect(onError).toHaveBeenCalled());
    expect(onError.mock.calls[0][0].message).toContain("401");
  });
});
