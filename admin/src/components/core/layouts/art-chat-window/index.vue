<!-- 系统聊天窗口（admin 智能助手：模拟问答，切换应用看提问效果） -->
<template>
  <div>
    <ElDrawer v-model="isDrawerVisible" :size="isMobile ? '100%' : '480px'" :with-header="false">
      <div class="mb-4 flex-cb">
        <div>
          <span class="text-base font-medium">Art Bot</span>
          <div class="mt-1.5 flex-c gap-1">
            <div
              class="h-2 w-2 rounded-full"
              :class="isOnline ? 'bg-success/100' : 'bg-danger/100'"
            ></div>
            <span class="text-xs text-g-600">{{
              isOnline ? $t('everkb.assistant.online') : $t('everkb.assistant.offline')
            }}</span>
          </div>
        </div>
        <div>
          <ElIcon class="c-p" :size="20" @click="closeChat">
            <Close />
          </ElIcon>
        </div>
      </div>

      <!-- 应用选择器：管理员切换要模拟的应用 -->
      <div class="mb-3">
        <div class="mb-1.5 text-xs text-g-600">{{ $t('everkb.assistant.simulateApp') }}</div>
        <ElSelect
          v-model="selectedAppId"
          :loading="appLoading"
          :placeholder="$t('everkb.assistant.selectAppPlaceholder')"
          filterable
          class="w-full"
          @change="handleAppChange"
        >
          <ElOption
            v-for="app in appList"
            :key="app.id"
            :label="app.name"
            :value="app.id"
            :disabled="!app.enabled"
          >
            <span class="flex-cb">
              <span>{{ app.name }}</span>
              <span v-if="!app.enabled" class="text-xs text-g-500">
                （{{ $t('everkb.assistant.appDisabled') }}）
              </span>
            </span>
          </ElOption>
        </ElSelect>
      </div>

      <div class="flex h-[calc(100%-140px)] flex-col">
        <!-- 聊天消息区域 -->
        <div
          class="flex-1 overflow-y-auto border-t-d px-4 py-7.5 [&::-webkit-scrollbar]:!w-1"
          ref="messageContainer"
        >
          <template v-for="message in messages" :key="message.id">
            <div
              :class="[
                'mb-7.5 flex w-full items-start gap-2',
                message.isMe ? 'flex-row-reverse' : 'flex-row'
              ]"
            >
              <ElAvatar :size="32" :src="message.avatar" class="shrink-0" />
              <div
                :class="['flex max-w-[75%] flex-col', message.isMe ? 'items-end' : 'items-start']"
              >
                <div
                  :class="[
                    'mb-1 flex gap-2 text-xs',
                    message.isMe ? 'flex-row-reverse' : 'flex-row'
                  ]"
                >
                  <span class="font-medium">{{ message.sender }}</span>
                  <span class="text-g-600">{{ message.time }}</span>
                </div>

                <!-- 气泡：普通文本 / 流式中打字机 / 错误 -->
                <div
                  :class="[
                    'rounded-md px-3.5 py-2.5 text-sm leading-[1.5]',
                    message.isMe
                      ? 'message-right bg-theme/15 text-g-900'
                      : 'message-left bg-g-300/50 text-g-900'
                  ]"
                >
                  <span v-if="message.content" class="whitespace-pre-wrap">{{
                    message.content
                  }}</span>
                  <span v-if="message.streaming && !message.content" class="text-g-500 italic">
                    {{ $t('everkb.assistant.thinking') }}
                  </span>
                  <span v-if="message.streaming && message.content" class="text-theme">▍</span>
                  <span v-else-if="message.error" class="text-danger">{{ message.error }}</span>
                </div>

                <!-- 引用溯源卡片（仅 AI 回答完成后，有引用时） -->
                <div
                  v-if="
                    !message.isMe &&
                    !message.streaming &&
                    !message.error &&
                    message.citations.length > 0
                  "
                  class="mt-2 w-full"
                >
                  <div class="mb-1.5 text-xs font-medium text-g-700">
                    {{ $t('everkb.assistant.citations', { n: message.citations.length }) }}
                  </div>
                  <div class="citation-list">
                    <div v-for="(c, i) in message.citations" :key="i" class="citation-item">
                      <div class="citation-head">
                        <span class="citation-index">[{{ i + 1 }}]</span>
                        <span class="citation-name">{{
                          c.doc_name || $t('everkb.assistant.docNumber', { n: c.doc_id })
                        }}</span>
                        <span v-if="c.page_number != null" class="citation-page">
                          {{ $t('everkb.assistant.pageN', { n: c.page_number }) }}
                        </span>
                        <span class="citation-score">{{ c.score.toFixed(3) }}</span>
                      </div>
                      <div class="citation-snippet">{{ c.snippet }}</div>
                      <a
                        v-if="c.source_url"
                        class="citation-url"
                        :href="c.source_url"
                        target="_blank"
                        rel="noopener noreferrer"
                      >
                        {{ $t('everkb.assistant.viewSource') }}
                      </a>
                    </div>
                  </div>
                </div>

                <!-- grounded=false 提示 -->
                <div
                  v-if="
                    !message.isMe &&
                    !message.streaming &&
                    !message.error &&
                    message.grounded === false
                  "
                  class="mt-1 text-xs text-warning"
                >
                  {{ $t('everkb.assistant.ungrounded') }}
                </div>
              </div>
            </div>
          </template>
        </div>

        <!-- 聊天输入区域 -->
        <div class="px-4 pt-4">
          <ElInput
            v-model="messageText"
            type="textarea"
            :rows="3"
            :placeholder="$t('everkb.assistant.inputPlaceholder')"
            resize="none"
            :disabled="isStreaming"
            @keyup.enter.exact.prevent="sendMessage"
          >
            <template #append>
              <div class="flex gap-2 py-2">
                <ElButton type="primary" :disabled="!canSend" @click="sendMessage" v-ripple>
                  {{
                    isStreaming ? $t('everkb.assistant.generating') : $t('everkb.assistant.send')
                  }}
                </ElButton>
              </div>
            </template>
          </ElInput>
          <div class="mt-3 flex-cb">
            <ElButton link type="info" size="small" @click="stopStream">
              <template v-if="isStreaming">{{ $t('everkb.assistant.stopGenerating') }}</template>
              <template v-else>{{ $t('everkb.assistant.clearChat') }}</template>
            </ElButton>
            <ElButton
              type="primary"
              :disabled="!canSend"
              @click="sendMessage"
              v-ripple
              class="min-w-20"
            >
              {{ $t('everkb.assistant.send') }}
            </ElButton>
          </div>
        </div>
      </div>
    </ElDrawer>
  </div>
</template>

<script setup lang="ts">
  import { Close } from '@element-plus/icons-vue'
  import { ElMessage } from 'element-plus'
  import { mittBus } from '@/utils/sys'
  import { fetchAppList } from '@/api/everkb/app'
  import { streamAssistantChat, type AssistantChatDone } from '@/api/everkb/assistant'
  import { useAssistantStore } from '@/store/modules/assistant'
  import meAvatar from '@/assets/images/avatar/avatar5.webp'
  import aiAvatar from '@/assets/images/avatar/avatar10.webp'

  defineOptions({ name: 'ArtChatWindow' })

  // 常量定义
  const MOBILE_BREAKPOINT = 640
  const SCROLL_DELAY = 100
  const BOT_NAME = 'Art Bot'
  const USER_NAME = 'Ricky'

  // 响应式布局
  const { width } = useWindowSize()
  const isMobile = computed(() => width.value < MOBILE_BREAKPOINT)

  // 组件状态
  const isDrawerVisible = ref(false)
  const isOnline = ref(true)

  // 会话状态（pinia 持久化：关闭抽屉/刷新后对话与应用选择仍在）
  const assistantStore = useAssistantStore()
  const messages = computed(() => assistantStore.messages)
  const isStreaming = computed(() => assistantStore.isStreaming)
  const selectedAppId = computed({
    get: () => assistantStore.selectedAppId,
    set: (v) => assistantStore.setSelectedAppId(v)
  })

  // 应用选择器状态（运行时，不持久化）
  const appList = ref<Api.EverKB.App[]>([])
  const appLoading = ref(false)

  // 消息输入与滚动
  const messageText = ref('')
  const messageContainer = ref<HTMLElement | null>(null)

  // 流式取消句柄（运行时，不持久化）
  let activeHandle: { abort: () => void } | null = null

  const canSend = computed(
    () => !isStreaming.value && messageText.value.trim().length > 0 && selectedAppId.value != null
  )

  // ── 工具函数 ───────────────────────────────────────────────────
  const formatCurrentTime = (): string => {
    return new Date().toLocaleTimeString([], {
      hour: '2-digit',
      minute: '2-digit'
    })
  }

  // 生成自增消息 id：基于已有消息的最大 id 续增，避免刷新后与持久化 id 冲突
  const nextMessageId = (): number => {
    const max = assistantStore.messages.reduce((m, msg) => Math.max(m, msg.id), 0)
    return max + 1
  }

  const scrollToBottom = (): void => {
    nextTick(() => {
      setTimeout(() => {
        if (messageContainer.value) {
          messageContainer.value.scrollTop = messageContainer.value.scrollHeight
        }
      }, SCROLL_DELAY)
    })
  }

  // ── 应用列表 ───────────────────────────────────────────────────
  const loadApps = async () => {
    appLoading.value = true
    try {
      appList.value = await fetchAppList()
      // 默认选中第一个启用的应用；否则选第一个（即使停用）
      if (selectedAppId.value == null && appList.value.length > 0) {
        const firstEnabled = appList.value.find((a) => a.enabled)
        assistantStore.setSelectedAppId((firstEnabled ?? appList.value[0]).id)
      }
    } catch {
      // 错误已由 http 层弹出
    } finally {
      appLoading.value = false
    }
  }

  const handleAppChange = () => {
    // 切换应用：清空对话，重新以新应用视角提问
    assistantStore.clearMessages()
  }

  // ── 消息处理 ───────────────────────────────────────────────────
  const sendMessage = (): void => {
    const text = messageText.value.trim()
    if (!text || isStreaming.value || selectedAppId.value == null) return

    const appId = selectedAppId.value
    const appName = appList.value.find((a) => a.id === appId)?.name ?? `#${appId}`

    // 用户消息
    assistantStore.pushMessage({
      id: nextMessageId(),
      sender: USER_NAME,
      content: text,
      time: formatCurrentTime(),
      isMe: true,
      avatar: meAvatar,
      streaming: false,
      error: '',
      grounded: null,
      citations: []
    })

    // AI 占位消息（流式填充）
    const aiMessageId = nextMessageId()
    assistantStore.pushMessage({
      id: aiMessageId,
      sender: `${BOT_NAME} · ${appName}`,
      content: '',
      time: formatCurrentTime(),
      isMe: false,
      avatar: aiAvatar,
      streaming: true,
      error: '',
      grounded: null,
      citations: []
    })

    messageText.value = ''
    assistantStore.setStreaming(true)
    scrollToBottom()

    const aiMessage = assistantStore.findMessage(aiMessageId)!

    activeHandle = streamAssistantChat(
      { app_id: appId, question: text },
      {
        onDelta: (delta) => {
          aiMessage.content += delta
          scrollToBottom()
        },
        onDone: (event: AssistantChatDone) => {
          aiMessage.streaming = false
          aiMessage.grounded = event.grounded
          aiMessage.citations = event.citations
          assistantStore.setStreaming(false)
          activeHandle = null
          scrollToBottom()
        },
        onError: (err) => {
          aiMessage.streaming = false
          aiMessage.error = err.message
          assistantStore.setStreaming(false)
          activeHandle = null
          ElMessage.error(err.message)
          scrollToBottom()
        }
      }
    )
  }

  const stopStream = (): void => {
    if (isStreaming.value) {
      activeHandle?.abort()
      assistantStore.setStreaming(false)
      activeHandle = null
      // 给当前流式消息收尾
      const last = assistantStore.messages[assistantStore.messages.length - 1]
      if (last && !last.isMe && last.streaming) {
        last.streaming = false
      }
    } else {
      assistantStore.clearMessages()
    }
  }

  // ── 聊天窗口控制 ───────────────────────────────────────────────
  const openChat = (): void => {
    isDrawerVisible.value = true
    if (appList.value.length === 0) {
      void loadApps()
    }
    scrollToBottom()
  }

  const closeChat = (): void => {
    isDrawerVisible.value = false
  }

  // 生命周期：组件挂载时兜底清理持久化残留的"流式中"消息（刷新后不可能还在生成）
  onMounted(() => {
    mittBus.on('openChat', openChat)
    assistantStore.messages.forEach((m) => {
      if (m.streaming) m.streaming = false
    })
  })

  onUnmounted(() => {
    mittBus.off('openChat', openChat)
    activeHandle?.abort()
  })
</script>

<style lang="scss" scoped>
  .citation-list {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .citation-item {
    padding: 8px 10px;
    border: 1px solid var(--art-border-color-light, #ebeef5);
    border-radius: 6px;
    background: var(--art-fill-color-blank, #fff);

    .citation-head {
      display: flex;
      align-items: center;
      gap: 6px;
      margin-bottom: 4px;
      font-size: 12px;
    }

    .citation-index {
      color: var(--art-color-primary, #409eff);
      font-weight: 600;
    }

    .citation-name {
      font-weight: 600;
      max-width: 40%;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    .citation-page {
      color: var(--art-gray-500, #909399);
    }

    .citation-score {
      margin-left: auto;
      color: var(--art-color-success, #67c23a);
      font-weight: 600;
    }

    .citation-snippet {
      font-size: 12px;
      color: var(--art-gray-600, #888);
      line-height: 1.6;
      word-break: break-word;
    }

    .citation-url {
      display: inline-block;
      margin-top: 4px;
      font-size: 12px;
      color: var(--art-color-primary, #409eff);
      text-decoration: none;
    }
  }
</style>
