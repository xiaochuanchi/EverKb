/**
 * chat-kit 入口（F3）：导出对话核心的可挂载组件、store 工厂与流式客户端。
 * 边界铁律见同目录 README.md（禁止依赖门户壳 / element-plus / api 单例）。
 */

export { default as ChatKit } from "./ChatKit.vue";
export { useChatStore, createChatStore, createSender, type ChatStore } from "./store";
export { streamChat, parseSseBuffer } from "./sse";
export type {
  ChatMessage,
  ChatKitOptions,
  Citation,
  ChatStreamEvent,
  ChatDeltaEvent,
  ChatDoneEvent,
  StreamHandlers,
} from "./types";
export { isDoneEvent } from "./types";
