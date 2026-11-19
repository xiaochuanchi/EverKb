<!-- 通知中心组件 -->
<template>
  <div
    class="art-notification-panel art-card-sm !shadow-xl"
    :style="{
      transform: show ? 'scaleY(1)' : 'scaleY(0.9)',
      opacity: show ? 1 : 0
    }"
    v-show="visible"
    @click.stop
  >
    <div class="flex-cb px-3.5 mt-3.5">
      <span class="text-base font-medium text-g-800">{{ $t('notice.title') }}</span>
      <span
        class="text-xs text-g-800 px-1.5 py-1 c-p select-none rounded hover:bg-g-200"
        @click="handleReadAll"
      >
        {{ $t('notice.btnReadAll') }}
      </span>
    </div>

    <div class="w-full h-[calc(100%-48px)]">
      <div class="h-[calc(100%-60px)] overflow-y-scroll scrollbar-thin">
        <!-- 通知列表 -->
        <ul v-if="notifications.length > 0">
          <li
            v-for="item in notifications"
            :key="item.id"
            class="box-border flex-c px-3.5 py-3.5 c-p last:border-b-0 hover:bg-g-200/60"
            :class="{ 'opacity-60': item.is_read }"
            @click="handleItemClick(item)"
          >
            <div
              class="size-9 leading-9 text-center rounded-lg flex-cc"
              :class="getIconClass(item.type)"
            >
              <ArtSvgIcon class="text-lg !bg-transparent" :icon="getIcon(item.type)" />
            </div>
            <div class="w-[calc(100%-45px)] ml-3.5">
              <h4 class="text-sm font-normal leading-5.5 text-g-900">{{ item.title }}</h4>
              <p class="mt-1 text-xs text-g-500 line-clamp-2">{{ item.content }}</p>
              <p class="mt-1 text-xs text-g-400">{{ formatTime(item.created_at) }}</p>
            </div>
            <!-- 未读红点 -->
            <div v-if="!item.is_read" class="ml-2 size-2 !bg-danger rounded-full shrink-0"></div>
          </li>
        </ul>

        <!-- 空状态 -->
        <div v-else class="relative top-25 h-full text-g-500 text-center !bg-transparent">
          <ArtSvgIcon icon="system-uicons:inbox" class="text-5xl" />
          <p class="mt-3.5 text-xs !bg-transparent">{{ $t('notice.empty') }}</p>
        </div>
      </div>

      <div class="relative box-border w-full px-3.5">
        <ElButton class="w-full mt-3" :loading="loading" @click="handleViewAll" v-ripple>
          {{ $t('notice.viewAll') }}
        </ElButton>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
  import { ref, watch } from 'vue'
  import { useRouter } from 'vue-router'
  import { ElMessage } from 'element-plus'
  import {
    fetchNotifications,
    fetchUnreadCount,
    markAllNotificationsRead,
    markNotificationRead
  } from '@/api/everkb/notification'

  defineOptions({ name: 'ArtNotification' })

  const props = defineProps<{
    value: boolean
  }>()

  const emit = defineEmits<{
    'update:value': [value: boolean]
    'unread-change': [unread: number]
  }>()

  const router = useRouter()

  const show = ref(false)
  const visible = ref(false)
  const notifications = ref<Api.EverKB.Notification[]>([])
  const loading = ref(false)

  // ── 图标与样式映射 ─────────────────────────────────────────────
  const getIcon = (type: string): string => {
    return type === 'doc_failed' ? 'ri:error-warning-line' : 'ri:file-list-3-line'
  }

  const getIconClass = (type: string): string => {
    return type === 'doc_failed' ? 'bg-danger/12 text-danger' : 'bg-theme/12 text-theme'
  }

  const formatTime = (iso: string): string => {
    if (!iso) return ''
    const d = new Date(iso)
    const pad = (n: number) => String(n).padStart(2, '0')
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
  }

  // ── 数据加载 ───────────────────────────────────────────────────
  const loadNotifications = async () => {
    loading.value = true
    try {
      const page = await fetchNotifications({ page: 1, size: 50 })
      notifications.value = page.items
      // 通知未读数回传父组件，驱动铃铛红点
      emit('unread-change', page.unread)
    } catch {
      // 错误已由 http 层弹出
    } finally {
      loading.value = false
    }
  }

  // ── 交互 ───────────────────────────────────────────────────────
  const handleItemClick = async (item: Api.EverKB.Notification) => {
    // 标记已读
    if (!item.is_read) {
      try {
        await markNotificationRead(item.id)
        item.is_read = true
        // 刷新未读数
        const { unread } = await fetchUnreadCount()
        emit('unread-change', unread)
      } catch {
        // 已读标记失败不阻断跳转
      }
    }
    // 跳转到对应文档
    if (item.resource_type === 'document' && item.resource_id != null) {
      router.push({ path: '/everkb/document', query: { docId: String(item.resource_id) } })
    }
    emit('update:value', false)
  }

  const handleReadAll = async () => {
    if (notifications.value.length === 0) return
    try {
      await markAllNotificationsRead()
      notifications.value.forEach((n) => (n.is_read = true))
      emit('unread-change', 0)
    } catch {
      ElMessage.error('操作失败')
    }
  }

  const handleViewAll = () => {
    emit('update:value', false)
  }

  // ── 动画 ───────────────────────────────────────────────────────
  const showNotice = (open: boolean) => {
    if (open) {
      visible.value = true
      void loadNotifications()
      setTimeout(() => {
        show.value = true
      }, 5)
    } else {
      show.value = false
      setTimeout(() => {
        visible.value = false
      }, 350)
    }
  }

  watch(
    () => props.value,
    (newValue) => {
      showNotice(newValue)
    }
  )
</script>

<style scoped>
  @reference '@styles/core/tailwind.css';

  .art-notification-panel {
    @apply absolute 
    top-14.5 
    right-5 
    w-90 
    h-125 
    overflow-hidden 
    transition-all 
    duration-300
    origin-top 
    will-change-[top,left] 
    max-[640px]:top-[65px]
    max-[640px]:right-0
    max-[640px]:w-full 
    max-[640px]:h-[80vh];
  }

  .scrollbar-thin::-webkit-scrollbar {
    width: 5px !important;
  }

  .dark .scrollbar-thin::-webkit-scrollbar-track {
    background-color: var(--default-box-color);
  }

  .dark .scrollbar-thin::-webkit-scrollbar-thumb {
    background-color: #222 !important;
  }
</style>
