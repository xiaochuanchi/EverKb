/**
 * chat-kit 类型契约（F3）。
 *
 * 与后端 open 侧问答协议对齐（backend/app/api/open.py）：
 * - 请求体：{ question, user_key }（X-API-Key 鉴权）
 * - SSE data 帧：{ delta } 流式增量；收尾帧 { grounded, citations }
 * - citations 元素：doc_name/doc_id/chunk_id/page_number/snippet/score/source_url
 */

/** 单条引用（对齐 backend rag.build_context 的 citations 契约） */
export interface Citation {
  doc_name: string;
  doc_id: number;
  chunk_id: number;
  page_number: number | null;
  snippet: string;
  score: number;
  source_url: string | null;
}

/** SSE 流式增量帧 */
export interface ChatDeltaEvent {
  delta: string;
}

/** SSE 收尾帧：grounded 依据 + 引用清单 */
export interface ChatDoneEvent {
  grounded: boolean;
  citations: Citation[];
}

/** SSE 帧联合类型 */
export type ChatStreamEvent = ChatDeltaEvent | ChatDoneEvent;

/** 判断是否为收尾帧（有 grounded 字段） */
export function isDoneEvent(e: ChatStreamEvent): e is ChatDoneEvent {
  return "grounded" in e && "citations" in e;
}

/** 一条对话消息 */
export interface ChatMessage {
  /** 客户端生成的唯一 id（流式过程中稳定，用于定位追加 delta） */
  id: string;
  role: "user" | "assistant";
  content: string;
  /** 回答是否基于知识库（仅 assistant 消息有意义，自由回答为 false） */
  grounded: boolean;
  /** 引用清单（仅 assistant 消息，收尾帧填充） */
  citations: Citation[];
  /** 是否仍在流式生成中 */
  streaming: boolean;
  /** 出错信息（生成中断时展示） */
  error?: string;
}

/** 发起一轮问答所需的运行参数（由挂载方注入，chat-kit 不感知从哪来） */
export interface ChatKitOptions {
  /** 后端 open 问答端点基址，如 /api/v1/apps/{app_id}/chat */
  appId: number;
  /** 应用 api_key（X-API-Key 头，明文） */
  apiKey: string;
  /** 可选：自定义 fetch 实现（测试注入 fake），默认全局 fetch */
  fetchImpl?: typeof fetch;
  /** 可选：user_key（用户侧标识，透传后端） */
  userKey?: string;
}

/**
 * 流式回调（SSE 客户端逐帧回调）。
 * onDelta 触发多次（打字机）；onDone 仅收尾帧触发一次；onError 中断时触发。
 */
export interface StreamHandlers {
  onDelta: (delta: string) => void;
  onDone: (event: ChatDoneEvent) => void;
  onError: (err: Error) => void;
}
