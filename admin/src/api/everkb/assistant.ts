import { useUserStore } from '@/store/modules/user'

/**
 * EverKB 智能助手 API（对齐后端 /api/v1/admin/assistant，机器人抽屉真问答）
 *
 * 与 open 侧问答（web/src/chat-kit）同协议，但走 admin JWT 鉴权：
 * - 端点：POST /api/v1/admin/assistant/chat（SSE 流式，退出统一信封）；
 * - 鉴权：Authorization: Bearer <token>（http 拦截器不覆盖原生 fetch，这里手动加）；
 * - 请求体：{ app_id, question }（管理员可切任意应用模拟提问）。
 *
 * SSE 协议（对齐 backend/app/api/open.py 的 _sse）：
 * - 每帧 `data: {json}\n\n`；事件 { delta } 增量 + 收尾 { grounded, citations }。
 */

/** SSE 收尾帧 */
export interface AssistantChatDone {
  grounded: boolean
  citations: Api.EverKB.Citation[]
}

/** 流式回调 */
export interface AssistantStreamHandlers {
  onDelta: (delta: string) => void
  onDone: (event: AssistantChatDone) => void
  onError: (err: Error) => void
}

/** 从原始 chunk 文本解析完整 SSE data 帧（跨 chunk 缓冲由调用方维护） */
function parseSseBuffer(buffer: string): {
  events: Array<{ delta?: string; grounded?: boolean; citations?: Api.EverKB.Citation[] }>
  remainder: string
} {
  const events: Array<{ delta?: string; grounded?: boolean; citations?: Api.EverKB.Citation[] }> =
    []
  let remainder = buffer
  let sep = remainder.indexOf('\n\n')

  while (sep !== -1) {
    const frame = remainder.slice(0, sep)
    remainder = remainder.slice(sep + 2)
    const dataLine = frame
      .split('\n')
      .map((l) => (l.startsWith('data:') ? l.slice(5).trimStart() : ''))
      .find((l) => l !== '')
    if (dataLine) {
      try {
        events.push(JSON.parse(dataLine))
      } catch {
        // 心跳/注释帧，跳过
      }
    }
    sep = remainder.indexOf('\n\n')
  }
  return { events, remainder }
}

/**
 * 发起管理员模拟问答（SSE 流式），返回可取消句柄。
 */
export function streamAssistantChat(
  body: Api.EverKB.AssistantChatRequest,
  handlers: AssistantStreamHandlers
): { abort: () => void } {
  const controller = new AbortController()
  const token = useUserStore().accessToken

  void (async () => {
    let res: Response
    try {
      res = await fetch('/api/v1/admin/assistant/chat', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: token.startsWith('Bearer ') ? token : `Bearer ${token}`
        },
        body: JSON.stringify(body),
        signal: controller.signal
      })
    } catch (err) {
      if (!(err instanceof DOMException && err.name === 'AbortError')) {
        handlers.onError(err instanceof Error ? err : new Error(String(err)))
      }
      return
    }

    if (!res.ok) {
      let message = `问答失败（HTTP ${res.status}）`
      try {
        const data = await res.json()
        message = data?.message || message
      } catch {
        // 非 JSON 错误体，用默认 message
      }
      handlers.onError(new Error(message))
      return
    }
    if (!res.body) {
      handlers.onError(new Error('响应不支持流式读取'))
      return
    }

    const reader = res.body.getReader()
    const decoder = new TextDecoder('utf-8')
    let buffer = ''

    const dispatch = (
      events: Array<{ delta?: string; grounded?: boolean; citations?: Api.EverKB.Citation[] }>
    ) => {
      for (const evt of events) {
        if (evt.grounded !== undefined && evt.citations) {
          handlers.onDone({ grounded: evt.grounded, citations: evt.citations })
        } else if (evt.delta !== undefined) {
          handlers.onDelta(evt.delta)
        }
      }
    }

    try {
      for (;;) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const { events, remainder } = parseSseBuffer(buffer)
        buffer = remainder
        dispatch(events)
      }
      const tail = decoder.decode()
      if (tail) {
        buffer += tail
        const { events } = parseSseBuffer(buffer)
        dispatch(events)
      }
    } catch (err) {
      if (!(err instanceof DOMException && err.name === 'AbortError')) {
        handlers.onError(err instanceof Error ? err : new Error(String(err)))
      }
    }
  })()

  return { abort: () => controller.abort() }
}
