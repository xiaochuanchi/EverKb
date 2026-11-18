/**
 * SSE 流式客户端（F3）。
 *
 * 架构约束：axios 不支持流式，此处用原生 fetch + ReadableStream 逐帧解析。
 * 不依赖 axios / element-plus / 门户壳单例，只依赖 types.ts 的纯类型契约。
 *
 * 协议（对齐 backend/app/api/open.py 的 _sse）：
 * - 每帧：`data: {json}\n\n`（JSON 用 ensure_ascii=false，可能含中文与换行）
 * - 事件类型：{ delta } 增量；收尾 { grounded, citations }
 * - 忽略 `data:` 前缀后的非 JSON 行（心跳/注释），健壮跳过
 */

import type { ChatStreamEvent, StreamHandlers } from "./types";
import { isDoneEvent } from "./types";

/** 从一段原始 chunk 文本里解析出完整的 SSE `data:` 帧（跨 chunk 缓冲由调用方维护） */
export function parseSseBuffer(buffer: string): {
  events: ChatStreamEvent[];
  remainder: string;
} {
  const events: ChatStreamEvent[] = [];
  // 按空行分隔帧（SSE 帧以 \n\n 结束）
  let remainder = buffer;
  let sep = remainder.indexOf("\n\n");

  while (sep !== -1) {
    const frame = remainder.slice(0, sep);
    remainder = remainder.slice(sep + 2);
    const event = parseSseFrame(frame);
    if (event !== null) {
      events.push(event);
    }
    sep = remainder.indexOf("\n\n");
  }

  return { events, remainder };
}

/** 解析单个 `data:` 帧，非法/心跳帧返回 null */
function parseSseFrame(frame: string): ChatStreamEvent | null {
  // 一个帧内可能有多行 `data:`（SSE 规范），这里后端只发单行，取第一个 data 行
  const lines = frame.split("\n");
  let dataLine = "";
  for (const line of lines) {
    if (line.startsWith("data:")) {
      dataLine = line.slice(5).trimStart();
      break;
    }
  }
  if (!dataLine) {
    // 空 data 或纯注释帧（心跳），跳过
    return null;
  }
  try {
    return JSON.parse(dataLine) as ChatStreamEvent;
  } catch {
    // 非 JSON 心跳/注释行，跳过
    return null;
  }
}

/**
 * 发起流式问答，返回一个可取消的句柄。
 *
 * @param url 完整请求 URL（含 app_id）
 * @param apiKey X-API-Key 头
 * @param body 请求体 { question, user_key }
 * @param handlers 流式回调
 */
export function streamChat(
  url: string,
  apiKey: string,
  body: { question: string; user_key: string },
  handlers: StreamHandlers,
  fetchImpl: typeof fetch = fetch,
): { abort: () => void } {
  const controller = new AbortController();

  void (async () => {
    let res: Response;
    try {
      res = await fetchImpl(url, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-API-Key": apiKey,
        },
        body: JSON.stringify(body),
        signal: controller.signal,
      });
    } catch (err) {
      // 主动 abort 会抛 AbortError，不视为错误；网络/其他异常上报
      if (!(err instanceof DOMException && err.name === "AbortError")) {
        handlers.onError(err instanceof Error ? err : new Error(String(err)));
      }
      return;
    }

    if (!res.ok) {
      handlers.onError(new Error(`问答失败（HTTP ${res.status}）`));
      return;
    }
    if (!res.body) {
      handlers.onError(new Error("响应不支持流式读取"));
      return;
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder("utf-8");
    let buffer = "";

    try {
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        const { events, remainder } = parseSseBuffer(buffer);
        buffer = remainder;
        for (const evt of events) {
          if (isDoneEvent(evt)) {
            handlers.onDone(evt);
          } else {
            handlers.onDelta(evt.delta);
          }
        }
      }
      // 流结束，flush 残余缓冲（部分后端最后无 \n\n，尽力解析）
      const tail = decoder.decode();
      if (tail) {
        buffer += tail;
        const { events } = parseSseBuffer(buffer);
        for (const evt of events) {
          if (isDoneEvent(evt)) {
            handlers.onDone(evt);
          } else {
            handlers.onDelta(evt.delta);
          }
        }
      }
    } catch (err) {
      if (!(err instanceof DOMException && err.name === "AbortError")) {
        handlers.onError(err instanceof Error ? err : new Error(String(err)));
      }
    }
  })();

  return { abort: () => controller.abort() };
}
