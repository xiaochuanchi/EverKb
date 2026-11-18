<template>
  <div class="editor-page">
    <!-- 顶栏：返回 + 文档信息 + 状态 + 保存 -->
    <div class="editor-toolbar art-card-sm">
      <ElButton circle @click="handleBack">
        <el-icon><ArrowLeft /></el-icon>
      </ElButton>
      <span class="doc-title" :title="doc?.name">{{ doc?.name || '文档编辑器' }}</span>
      <ElTag v-if="doc" :type="STATUS_META[doc.status]?.tag || 'info'" size="small">
        {{ STATUS_META[doc.status]?.label || `未知(${doc.status})` }}
      </ElTag>
      <ElTooltip v-if="doc?.edited" content="该文档的 markdown 已被人工编辑过" placement="top">
        <ElTag type="warning" size="small" effect="plain">已编辑</ElTag>
      </ElTooltip>

      <div class="toolbar-spacer" />

      <span v-if="polling" class="poll-hint">保存后重新切块向量化中…</span>
      <ElButton type="primary" :loading="saving" :disabled="polling || !doc" @click="handleSave">
        保存
      </ElButton>
    </div>

    <!-- 编辑器 -->
    <div v-if="loadError" class="editor-error">
      <ElEmpty :description="loadError" />
    </div>
    <div v-else class="editor-body art-card-sm">
      <MdEditor
        v-model="content"
        :theme="settingStore.isDark ? 'dark' : 'light'"
        :footers="['markdownTotal', 'scrollSwitch']"
        :toolbars="toolbars"
        placeholder="编辑文档 markdown 内容…"
        :style="{ height: 'calc(100vh - 160px)' }"
        @on-save="handleSave"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
  import { ElMessage } from 'element-plus'
  import { ArrowLeft } from '@element-plus/icons-vue'
  import { MdEditor, type ToolbarNames } from 'md-editor-v3'
  import 'md-editor-v3/lib/style.css'
  import { fetchDocumentContent, fetchDocumentDetail, saveDocumentContent } from '@/api/document'
  import { DOC_STATUS } from '@/constants/everkb'
  import { useSettingStore } from '@/store/modules/setting'

  defineOptions({ name: 'EverKBDocumentEditor' })

  const route = useRoute()
  const router = useRouter()
  const settingStore = useSettingStore()

  const STATUS_META: Record<
    number,
    { label: string; tag: 'info' | 'primary' | 'success' | 'warning' | 'danger' }
  > = {
    [DOC_STATUS.Uploaded]: { label: '已上传', tag: 'info' },
    [DOC_STATUS.Parsing]: { label: '解析中', tag: 'primary' },
    [DOC_STATUS.Extracted]: { label: '已抽取', tag: 'primary' },
    [DOC_STATUS.Chunked]: { label: '已切块', tag: 'primary' },
    [DOC_STATUS.Vectorizing]: { label: '向量化中', tag: 'warning' },
    [DOC_STATUS.Completed]: { label: '已完成', tag: 'success' },
    [DOC_STATUS.Failed]: { label: '失败', tag: 'danger' }
  }

  const docId = computed(() => Number(route.query.docId) || 0)
  const doc = ref<Api.EverKB.Document | null>(null)
  const content = ref('')
  const loadError = ref('')
  const saving = ref(false)
  const polling = ref(false)
  let pollTimer: ReturnType<typeof setInterval> | null = null

  const toolbars: ToolbarNames[] = [
    'bold',
    'underline',
    'italic',
    'strikeThrough',
    '-',
    'title',
    'quote',
    'unorderedList',
    'orderedList',
    '-',
    'codeRow',
    'code',
    'table',
    '-',
    'preview',
    'htmlPreview'
  ]

  const editable = (d: Api.EverKB.Document) =>
    d.status === DOC_STATUS.Extracted || d.status === DOC_STATUS.Completed

  const loadDoc = async () => {
    if (!docId.value) {
      loadError.value = '缺少 docId 参数'
      return
    }
    try {
      doc.value = await fetchDocumentDetail(docId.value)
    } catch {
      loadError.value = '文档不存在或已被删除'
      return
    }
    if (!editable(doc.value)) {
      loadError.value = '文档尚未生成 markdown 或处理中，暂不可编辑'
      return
    }
    try {
      const res = await fetchDocumentContent(docId.value)
      content.value = res.content
    } catch {
      loadError.value = 'markdown 内容加载失败'
    }
  }

  const handleSave = async () => {
    if (!docId.value) return
    saving.value = true
    try {
      doc.value = await saveDocumentContent(docId.value, content.value)
      startPolling()
    } catch {
      // http 层已弹错误
    } finally {
      saving.value = false
    }
  }

  /** 保存后轮询状态：worker 从切块续跑，直到 6（完成）或 7（失败） */
  const startPolling = () => {
    stopPolling()
    polling.value = true
    pollTimer = setInterval(async () => {
      try {
        const fresh = await fetchDocumentDetail(docId.value)
        doc.value = fresh
        if (fresh.status === DOC_STATUS.Completed) {
          stopPolling()
          ElMessage.success('重新切块向量化完成')
        } else if (fresh.status === DOC_STATUS.Failed) {
          stopPolling()
          ElMessage.error(`重新处理失败：${fresh.status_reason || '未知原因'}`)
        }
      } catch {
        stopPolling()
      }
    }, 3000)
  }

  const stopPolling = () => {
    if (pollTimer) {
      clearInterval(pollTimer)
      pollTimer = null
    }
    polling.value = false
  }

  const handleBack = () => {
    stopPolling()
    router.push('/everkb/document')
  }

  onMounted(() => {
    void loadDoc()
  })

  onUnmounted(() => {
    stopPolling()
  })
</script>

<style lang="scss" scoped>
  .editor-page {
    padding: 12px 16px;

    .editor-toolbar {
      display: flex;
      align-items: center;
      gap: 10px;
      padding: 10px 14px;
      margin-bottom: 12px;

      .doc-title {
        font-size: 14px;
        font-weight: 500;
        max-width: 360px;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
      }

      .toolbar-spacer {
        flex: 1;
      }

      .poll-hint {
        font-size: 12px;
        color: var(--art-gray-600, #888);
      }
    }

    .editor-body {
      padding: 8px;
    }

    .editor-error {
      background: var(--art-main-bg-color);
      border-radius: 8px;
      padding: 60px 0;
    }
  }
</style>
