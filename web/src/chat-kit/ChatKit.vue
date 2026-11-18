<script setup lang="ts">
/**
 * ChatKit 对话核心组件（F3）。
 *
 * 架构边界（tests/architecture.spec.ts 锁定）：
 * - 纯 Vue 组件，不 import element-plus / 门户壳单例 / @/router 等；
 * - pinia 实例由挂载方通过 props.pinia 传入（独立可挂载）；
 * - 流式经 sse.ts（原生 fetch），打字机渲染 delta。
 */

import { computed, nextTick, ref, watch, type PropType } from "vue";
import type { Pinia } from "pinia";

import { createChatStore, createSender, type ChatStore } from "./store";
import type { ChatKitOptions } from "./types";

const props = defineProps({
  /** 挂载方传入的 pinia 实例（门户壳传入其全局 pinia，embed widget 传入独立实例） */
  pinia: { type: Object as PropType<Pinia>, required: true },
  options: { type: Object as PropType<ChatKitOptions>, required: true },
});

const useKitStore = createChatStore(props.pinia);
const store: ChatStore = useKitStore();

const sender = createSender(store, { options: props.options });

// ── 输入与发送 ───────────────────────────────────────────────────
const draft = ref("");
const inputRef = ref<HTMLTextAreaElement | null>(null);
let activeHandle: { abort: () => void } | null = null;

const canSend = computed(() => draft.value.trim().length > 0 && !store.streaming);

function send(): void {
  const text = draft.value.trim();
  if (!text || store.streaming) return;
  draft.value = "";
  store.addUserMessage(text);
  activeHandle = sender.send(text);
}

function stop(): void {
  activeHandle?.abort();
  if (store.activeId) {
    store.abortAssistant(store.activeId);
  }
  activeHandle = null;
}

function clearChat(): void {
  if (store.streaming) {
    stop();
  }
  store.clear();
}

// ── 滚动到底部 ───────────────────────────────────────────────────
const listRef = ref<HTMLElement | null>(null);
watch(
  () => store.messages.map((m) => m.content.length).join(","),
  async () => {
    await nextTick();
    listRef.value?.scrollTo({ top: listRef.value.scrollHeight });
  },
);

// ── 键盘发送（Enter 发送，Shift+Enter 换行）─────────────────────
function onKeydown(e: KeyboardEvent): void {
  if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
    e.preventDefault();
    send();
  }
}
</script>

<template>
  <div class="chat-kit">
    <!-- 消息列表 -->
    <div ref="listRef" class="ck-messages">
      <div v-if="store.messages.length === 0" class="ck-empty">
        输入问题开始对话，回答将基于知识库并标注引用来源
      </div>

      <div
        v-for="msg in store.messages"
        :key="msg.id"
        class="ck-row"
        :class="msg.role === 'user' ? 'ck-row-user' : 'ck-row-assistant'"
      >
        <div class="ck-avatar">
          {{ msg.role === "user" ? "我" : "AI" }}
        </div>
        <div class="ck-bubble-wrap">
          <div class="ck-bubble" :class="`ck-bubble-${msg.role}`">
            <template v-if="msg.content">
              <span class="ck-content">{{ msg.content }}</span>
              <span v-if="msg.streaming" class="ck-cursor">▍</span>
            </template>
            <span v-else-if="msg.streaming" class="ck-thinking">思考中…</span>
            <span v-else-if="msg.error" class="ck-error">{{ msg.error }}</span>
          </div>

          <!-- 引用溯源卡片（仅 assistant 且非流式中，且有引用） -->
          <div
            v-if="msg.role === 'assistant' && !msg.streaming && msg.citations.length > 0"
            class="ck-citations"
          >
            <div class="ck-citations-title">引用来源（{{ msg.citations.length }}）</div>
            <details v-for="(c, i) in msg.citations" :key="i" class="ck-citation">
              <summary class="ck-citation-summary">
                <span class="ck-citation-index">[{{ i + 1 }}]</span>
                <span class="ck-citation-name">{{ c.doc_name || `文档 #${c.doc_id}` }}</span>
                <span v-if="c.page_number != null" class="ck-citation-page">第 {{ c.page_number }} 页</span>
                <span class="ck-citation-score">{{ c.score.toFixed(3) }}</span>
              </summary>
              <div class="ck-citation-body">
                <div class="ck-citation-snippet">{{ c.snippet }}</div>
                <a
                  v-if="c.source_url"
                  class="ck-citation-url"
                  :href="c.source_url"
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  查看原文
                </a>
              </div>
            </details>
          </div>

          <!-- grounded=false 提示 -->
          <div
            v-if="msg.role === 'assistant' && !msg.streaming && !msg.error && !msg.grounded"
            class="ck-ungrounded"
          >
            未基于知识库，自由回答
          </div>
        </div>
      </div>
    </div>

    <!-- 输入区 -->
    <div class="ck-inputbar">
      <div class="ck-inputbar-top">
        <button type="button" class="ck-clear" :disabled="store.messages.length === 0" @click="clearChat">
          清空
        </button>
      </div>
      <div class="ck-input-row">
        <textarea
          ref="inputRef"
          v-model="draft"
          class="ck-textarea"
          rows="2"
          placeholder="输入你的问题，Enter 发送，Shift+Enter 换行"
          @keydown="onKeydown"
        />
        <button v-if="store.streaming" type="button" class="ck-send ck-stop" @click="stop">
          停止
        </button>
        <button v-else type="button" class="ck-send" :disabled="!canSend" @click="send">
          发送
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.chat-kit {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
}

.ck-messages {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.ck-empty {
  margin: auto;
  color: #999;
  font-size: 13px;
}

.ck-row {
  display: flex;
  gap: 10px;
}

.ck-row-user {
  flex-direction: row-reverse;
}

.ck-avatar {
  flex-shrink: 0;
  width: 32px;
  height: 32px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 600;
  color: #fff;
}

.ck-row-user .ck-avatar {
  background: #409eff;
}

.ck-row-assistant .ck-avatar {
  background: #67c23a;
}

.ck-bubble-wrap {
  max-width: 78%;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.ck-row-user .ck-bubble-wrap {
  align-items: flex-end;
}

.ck-bubble {
  padding: 10px 14px;
  border-radius: 10px;
  font-size: 14px;
  line-height: 1.7;
  word-break: break-word;
  white-space: pre-wrap;
}

.ck-bubble-user {
  background: #409eff;
  color: #fff;
  border-top-right-radius: 2px;
}

.ck-bubble-assistant {
  background: #f5f7fa;
  color: #303133;
  border-top-left-radius: 2px;
}

.ck-content {
  white-space: pre-wrap;
}

.ck-cursor {
  display: inline-block;
  animation: ck-blink 0.8s infinite;
  color: #409eff;
}

@keyframes ck-blink {
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0;
  }
}

.ck-thinking {
  color: #999;
  font-style: italic;
}

.ck-error {
  color: #f56c6c;
}

.ck-citations {
  border: 1px solid #ebeef5;
  border-radius: 8px;
  overflow: hidden;
  background: #fff;
}

.ck-citations-title {
  padding: 8px 12px;
  font-size: 12px;
  font-weight: 600;
  color: #666;
  border-bottom: 1px solid #f0f2f5;
  background: #fafafa;
}

.ck-citation {
  border-bottom: 1px solid #f0f2f5;
}

.ck-citation:last-child {
  border-bottom: none;
}

.ck-citation-summary {
  padding: 8px 12px;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  list-style: none;
}

.ck-citation-summary::-webkit-details-marker {
  display: none;
}

.ck-citation-index {
  color: #409eff;
  font-weight: 600;
}

.ck-citation-name {
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 40%;
}

.ck-citation-page {
  font-size: 12px;
  color: #909399;
}

.ck-citation-score {
  margin-left: auto;
  font-size: 12px;
  color: #67c23a;
  font-weight: 600;
}

.ck-citation-body {
  padding: 0 12px 10px;
}

.ck-citation-snippet {
  font-size: 12px;
  color: #666;
  line-height: 1.6;
  word-break: break-word;
}

.ck-citation-url {
  display: inline-block;
  margin-top: 6px;
  font-size: 12px;
  color: #409eff;
  text-decoration: none;
}

.ck-ungrounded {
  font-size: 12px;
  color: #e6a23c;
  padding: 4px 2px;
}

.ck-inputbar {
  border-top: 1px solid #ebeef5;
  padding: 10px 16px 14px;
  background: #fff;
}

.ck-inputbar-top {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 6px;
}

.ck-clear {
  border: none;
  background: none;
  color: #909399;
  font-size: 12px;
  cursor: pointer;
  padding: 2px 4px;
}

.ck-clear:disabled {
  cursor: not-allowed;
  opacity: 0.5;
}

.ck-input-row {
  display: flex;
  gap: 10px;
  align-items: flex-end;
}

.ck-textarea {
  flex: 1;
  resize: none;
  border: 1px solid #dcdfe6;
  border-radius: 8px;
  padding: 10px 12px;
  font-size: 14px;
  line-height: 1.6;
  font-family: inherit;
  outline: none;
}

.ck-textarea:focus {
  border-color: #409eff;
}

.ck-send {
  border: none;
  background: #409eff;
  color: #fff;
  padding: 0 22px;
  height: 40px;
  border-radius: 8px;
  font-size: 14px;
  cursor: pointer;
  flex-shrink: 0;
}

.ck-send:disabled {
  background: #a0cfff;
  cursor: not-allowed;
}

.ck-stop {
  background: #f56c6c;
}
</style>
