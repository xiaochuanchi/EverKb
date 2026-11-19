/**
 * 智能助手（机器人抽屉）会话状态管理
 *
 * 持久化管理员在抽屉里的模拟问答对话，关闭抽屉 / 刷新页面后对话仍在。
 *
 * 持久化策略：
 * - messages、selectedAppId 持久化到 localStorage（版本化 key，见 store/index.ts）；
 * - isStreaming 不持久化——刷新后不可能仍在流式生成，运行时态单独管理。
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'

/** 抽屉内一条消息（对齐 art-chat-window/index.vue 的 ChatMessage） */
export interface AssistantMessage {
  id: number
  sender: string
  content: string
  time: string
  isMe: boolean
  avatar: string
  streaming: boolean
  error: string
  grounded: boolean | null
  citations: Api.EverKB.Citation[]
}

export const useAssistantStore = defineStore(
  'assistantStore',
  () => {
    /** 对话消息列表（持久化） */
    const messages = ref<AssistantMessage[]>([])
    /** 当前选中的应用 id（持久化，记住上次选择） */
    const selectedAppId = ref<number | null>(null)
    /** 是否正在流式生成（运行时态，不持久化） */
    const isStreaming = ref(false)

    /** 追加一条消息 */
    const pushMessage = (msg: AssistantMessage) => {
      messages.value.push(msg)
    }

    /** 按 id 查找消息（流式回调里定位当前生成中的消息） */
    const findMessage = (id: number) => messages.value.find((m) => m.id === id)

    /** 清空对话 */
    const clearMessages = () => {
      messages.value = []
    }

    /** 设置选中的应用 */
    const setSelectedAppId = (id: number | null) => {
      selectedAppId.value = id
    }

    /** 设置流式状态 */
    const setStreaming = (v: boolean) => {
      isStreaming.value = v
    }

    return {
      messages,
      selectedAppId,
      isStreaming,
      pushMessage,
      findMessage,
      clearMessages,
      setSelectedAppId,
      setStreaming
    }
  },
  {
    persist: {
      key: 'assistant',
      storage: localStorage,
      // 只持久化对话与应用选择；isStreaming 是运行时态，刷新后重置为 false
      pick: ['messages', 'selectedAppId']
    }
  }
)
