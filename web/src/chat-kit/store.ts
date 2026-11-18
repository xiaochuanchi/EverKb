/**
 * chat-kit 会话状态 store 工厂（F3）。
 *
 * 架构约束：chat-kit 不得 import 门户壳的 pinia 实例 / 单例，因此：
 * - `useChatStore` 是标准 defineStore（固定 id），在「已 install pinia」的组件内可直接用；
 * - `createChatStore(pinia)` 返回一个绑定了指定 pinia 实例的访问函数，供 embed widget
 *   传入其自有 `createPinia()` 实例（`useChatStore(pinia)`）独立挂载，与门户壳隔离。
 */

import { defineStore, type Pinia } from "pinia";

import { streamChat } from "./sse";
import type { ChatDoneEvent, ChatKitOptions, ChatMessage } from "./types";

export interface ChatStoreState {
  messages: ChatMessage[];
  /** 是否正在流式生成 */
  streaming: boolean;
  /** 当前正在生成的 assistant 消息 id */
  activeId: string | null;
}

let seq = 0;

function nextId(): string {
  seq += 1;
  return `msg_${Date.now()}_${seq}`;
}

export const useChatStore = defineStore("everkb-chat", {
  state: (): ChatStoreState => ({
    messages: [],
    streaming: false,
    activeId: null,
  }),

  actions: {
    /** 追加一条用户消息，返回其 id */
    addUserMessage(content: string): string {
      const msg: ChatMessage = {
        id: nextId(),
        role: "user",
        content,
        grounded: true,
        citations: [],
        streaming: false,
      };
      this.messages.push(msg);
      return msg.id;
    },

    /** 开启一条空的 assistant 消息（进入流式态），返回其 id */
    beginAssistant(): string {
      const msg: ChatMessage = {
        id: nextId(),
        role: "assistant",
        content: "",
        grounded: true,
        citations: [],
        streaming: true,
      };
      this.messages.push(msg);
      this.activeId = msg.id;
      this.streaming = true;
      return msg.id;
    },

    /** 流式增量追加 */
    appendDelta(id: string, delta: string): void {
      const msg = this.messages.find((m) => m.id === id);
      if (msg) {
        msg.content += delta;
      }
    },

    /** 流式结束：回填 grounded / citations */
    finishAssistant(id: string, event: ChatDoneEvent): void {
      const msg = this.messages.find((m) => m.id === id);
      if (msg) {
        msg.streaming = false;
        msg.grounded = event.grounded;
        msg.citations = event.citations;
      }
      this.streaming = false;
      this.activeId = null;
    },

    /** 流式中断（用户停止 / 网络异常）：标记错误或仅停止 */
    abortAssistant(id: string, error?: string): void {
      const msg = this.messages.find((m) => m.id === id);
      if (msg) {
        msg.streaming = false;
        if (error) {
          msg.error = error;
        }
      }
      this.streaming = false;
      this.activeId = null;
    },

    /** 清空会话 */
    clear(): void {
      this.messages = [];
      this.streaming = false;
      this.activeId = null;
    },
  },
});

/** store 实例类型 */
export type ChatStore = ReturnType<typeof useChatStore>;

/**
 * 绑定指定 pinia 实例的 store 访问函数（embed widget 独立挂载用）。
 * 用法：const useKit = createChatStore(myPinia); const store = useKit();
 */
export function createChatStore(pinia: Pinia) {
  return (): ChatStore => useChatStore(pinia);
}

/**
 * 发起一轮问答（store 层封装 SSE 客户端）。
 * 返回取消句柄，供「停止」按钮调用。
 */
export interface SendQuestionDeps {
  options: ChatKitOptions;
  fetchImpl?: typeof fetch;
}

export function createSender(
  store: ChatStore,
  deps: SendQuestionDeps,
): { send: (question: string) => { abort: () => void } } {
  const { appId, apiKey, userKey = "" } = deps.options;
  const url = `/api/v1/apps/${appId}/chat`;

  return {
    send(question: string) {
      const assistantId = store.beginAssistant();
      const handle = streamChat(
        url,
        apiKey,
        { question, user_key: userKey },
        {
          onDelta: (delta) => store.appendDelta(assistantId, delta),
          onDone: (event) => store.finishAssistant(assistantId, event),
          onError: (err) => store.abortAssistant(assistantId, err.message),
        },
        deps.fetchImpl,
      );
      return handle;
    },
  };
}
