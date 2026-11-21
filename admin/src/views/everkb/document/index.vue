<template>
  <div class="doc-page">
    <!-- 工具条：知识库选择 + 状态过滤 + 上传/网页/刷新 -->
    <div class="toolbar art-card-sm">
      <div class="toolbar-left">
        <span class="toolbar-label">{{ $t('everkb.document.knowledgeBase') }}</span>
        <ElSelect
          v-model="currentKbId"
          :loading="kbLoading"
          :placeholder="$t('everkb.document.selectKnowledgeBase')"
          style="width: 220px"
          @change="handleKbChange"
        >
          <ElOption v-for="kb in kbList" :key="kb.id" :label="kb.name" :value="kb.id" />
        </ElSelect>

        <span class="toolbar-label">{{ $t('everkb.document.status') }}</span>
        <ElSelect
          v-model="statusFilter"
          :placeholder="$t('everkb.document.all')"
          clearable
          style="width: 140px"
          @change="handleStatusFilter"
        >
          <ElOption
            v-for="(meta, status) in STATUS_META"
            :key="status"
            :label="meta.label"
            :value="Number(status)"
          />
        </ElSelect>

        <ElTooltip :content="$t('everkb.document.autoRefreshTip')" placement="top">
          <ElSwitch
            v-model="autoRefresh"
            inline-prompt
            :active-text="$t('everkb.document.auto')"
            :inactive-text="$t('everkb.document.manual')"
          />
        </ElTooltip>
      </div>

      <div class="toolbar-right">
        <ElButton type="primary" :disabled="!currentKbId" @click="openUpload">
          <el-icon class="mr-1"><Upload /></el-icon>
          {{ $t('everkb.document.uploadDocument') }}
        </ElButton>
        <ElButton :disabled="!currentKbId" @click="openWebDialog">
          <el-icon class="mr-1"><Link /></el-icon>
          {{ $t('everkb.document.addWebpage') }}
        </ElButton>
        <ElButton circle :disabled="!currentKbId" @click="refreshData">
          <el-icon><Refresh /></el-icon>
        </ElButton>
      </div>
    </div>

    <ArtTable
      :columns="columns"
      :data="data"
      :loading="loading"
      :pagination="pagination"
      :paginationOptions="{ pageSizes: [20, 50, 100], hideOnSinglePage: false }"
      empty-height="420"
      :emptyText="
        currentKbId ? $t('everkb.document.emptyNoDocs') : $t('everkb.document.emptySelectKb')
      "
      @pagination:size-change="handleSizeChange"
      @pagination:current-change="handleCurrentChange"
    >
      <template #name="{ row }">
        <div class="doc-name">
          <el-icon class="doc-name-icon"><Document /></el-icon>
          <span class="doc-name-text" :title="row.name">{{ row.name }}</span>
          <ElTag v-if="row.edited" size="small" type="warning" effect="plain">
            {{ $t('everkb.document.edited') }}
          </ElTag>
          <ElTag v-if="row.version > 1" size="small" effect="plain">v{{ row.version }}</ElTag>
        </div>
      </template>

      <template #status="{ row }">
        <ElTooltip
          v-if="row.status === DOC_STATUS.Failed && row.status_reason"
          :content="row.status_reason"
          placement="top"
          :show-after="100"
        >
          <ElTag :type="STATUS_META[row.status].tag" size="small">
            {{ STATUS_META[row.status].label }}
          </ElTag>
        </ElTooltip>
        <ElTag v-else :type="STATUS_META[row.status]?.tag || 'info'" size="small">
          {{
            STATUS_META[row.status]?.label ||
            $t('everkb.document.unknownStatus', { status: row.status })
          }}
        </ElTag>
      </template>

      <template #source_type="{ row }">
        <ElTag
          size="small"
          effect="plain"
          :type="row.source_type === DOC_SOURCE_TYPE.Webpage ? 'success' : 'info'"
        >
          {{
            row.source_type === DOC_SOURCE_TYPE.Webpage
              ? $t('everkb.document.sourceWebpage')
              : $t('everkb.document.sourceUpload')
          }}
        </ElTag>
      </template>

      <template #enabled="{ row }">
        <ElSwitch
          :model-value="row.enabled"
          :disabled="isProcessing(row)"
          @change="(v) => handleToggleEnabled(row, Boolean(v))"
        />
      </template>

      <template #actions="{ row }">
        <ElButton
          v-if="row.status >= DOC_STATUS.Extracted"
          link
          type="primary"
          @click="openEditor(row)"
        >
          {{ $t('everkb.document.edit') }}
        </ElButton>
        <ElButton
          v-if="row.source_type === DOC_SOURCE_TYPE.Upload && !isProcessing(row)"
          link
          type="primary"
          @click="openReplace(row)"
        >
          {{ $t('everkb.document.replace') }}
        </ElButton>
        <ElButton
          v-if="row.status === DOC_STATUS.Failed"
          link
          type="warning"
          @click="handleRetry(row)"
        >
          {{ $t('everkb.document.retry') }}
        </ElButton>
        <ElButton link type="primary" @click="openPreview(row)">
          {{ $t('everkb.document.preview') }}
        </ElButton>
        <ElButton
          v-if="row.status >= DOC_STATUS.Extracted"
          link
          type="primary"
          @click="openChunks(row)"
        >
          {{ $t('everkb.document.chunks') }}
        </ElButton>
        <ElButton v-if="!isProcessing(row)" link type="danger" @click="handleDelete(row)">
          {{ $t('everkb.document.delete') }}
        </ElButton>
      </template>
    </ArtTable>

    <!-- 上传文档弹窗 -->
    <ElDialog
      v-model="uploadVisible"
      :title="$t('everkb.document.uploadDocument')"
      width="480px"
      :close-on-click-modal="false"
    >
      <ElUpload
        v-model:file-list="uploadFileList"
        drag
        multiple
        :auto-upload="false"
        :limit="UPLOAD_LIMIT"
        :on-exceed="handleUploadExceed"
        accept=".docx,.pdf,.xlsx,.txt,.md,.csv,.html"
      >
        <el-icon :size="40" class="upload-icon"><UploadFilled /></el-icon>
        <div class="el-upload__text"
          >{{ $t('everkb.document.dragHere') }}
          <em>{{ $t('everkb.document.clickSelect') }}</em></div
        >
        <template #tip>
          <div class="el-upload__tip">{{ $t('everkb.document.uploadTip') }}</div>
        </template>
      </ElUpload>
      <template #footer>
        <ElButton @click="uploadVisible = false">{{ $t('everkb.document.cancel') }}</ElButton>
        <ElButton
          type="primary"
          :loading="uploading"
          :disabled="!uploadFileList.length"
          @click="handleUpload"
        >
          {{ $t('everkb.document.upload') }}
        </ElButton>
      </template>
    </ElDialog>

    <!-- 替换重传弹窗 -->
    <ElDialog
      v-model="replaceVisible"
      :title="$t('everkb.document.replaceFile')"
      width="480px"
      :close-on-click-modal="false"
    >
      <I18nT keypath="everkb.document.replaceTip" tag="p" class="replace-tip" scope="global">
        <template #name>
          <b>{{ replacingDoc?.name }}</b>
        </template>
      </I18nT>
      <ElUpload
        v-model:file-list="replaceFileList"
        drag
        :auto-upload="false"
        :limit="1"
        accept=".docx,.pdf,.xlsx,.txt,.md,.csv,.html"
      >
        <el-icon :size="40" class="upload-icon"><UploadFilled /></el-icon>
        <div class="el-upload__text"
          >{{ $t('everkb.document.dragNewHere') }}
          <em>{{ $t('everkb.document.clickSelect') }}</em></div
        >
        <template #tip>
          <div class="el-upload__tip">{{ $t('everkb.document.uploadTip') }}</div>
        </template>
      </ElUpload>
      <template #footer>
        <ElButton @click="replaceVisible = false">{{ $t('everkb.document.cancel') }}</ElButton>
        <ElButton
          type="primary"
          :loading="replacing"
          :disabled="!replaceFileList.length"
          @click="handleReplace"
        >
          {{ $t('everkb.document.replace') }}
        </ElButton>
      </template>
    </ElDialog>

    <!-- 批量添加网页弹窗 -->
    <ElDialog
      v-model="webVisible"
      :title="$t('everkb.document.addWebpages')"
      width="560px"
      :close-on-click-modal="false"
    >
      <ElInput
        v-model="webUrlsText"
        type="textarea"
        :rows="8"
        :placeholder="$t('everkb.document.webUrlsPlaceholder')"
      />
      <p class="web-count">{{ $t('everkb.document.enteredCount', { n: webUrlList.length }) }}</p>
      <template #footer>
        <ElButton @click="webVisible = false">{{ $t('everkb.document.cancel') }}</ElButton>
        <ElButton type="primary" :loading="webSubmitting" @click="handleWebSubmit">
          {{ $t('everkb.document.submit') }}
        </ElButton>
      </template>
    </ElDialog>

    <!-- 原文预览抽屉 -->
    <ElDrawer
      v-model="previewVisible"
      :title="previewDoc?.name || $t('everkb.document.previewTitle')"
      size="60%"
    >
      <div
        v-if="previewLoading"
        class="preview-loading"
        v-loading="true"
        :element-loading-text="$t('everkb.document.loading')"
      />
      <MdPreview
        v-else-if="previewContent"
        :model-value="previewContent"
        :theme="appStore.isDark ? 'dark' : 'light'"
      />
      <ElEmpty v-else :description="$t('everkb.document.noMarkdownContent')" />
    </ElDrawer>
  </div>
</template>

<script setup lang="ts">
  import { ElMessage, ElMessageBox } from 'element-plus'
  import type { UploadRawFile, UploadUserFile } from 'element-plus'
  import { I18nT, useI18n } from 'vue-i18n'
  import { Document, Link, Refresh, Upload, UploadFilled } from '@element-plus/icons-vue'
  import { MdPreview } from 'md-editor-v3'
  import 'md-editor-v3/lib/style.css'
  import {
    createWebDocuments,
    deleteDocument,
    fetchDocumentContent,
    fetchDocumentDetail,
    fetchDocumentPage,
    patchDocumentEnabled,
    replaceDocumentFile,
    retryDocument,
    uploadDocumentsBatch
  } from '@/api/document'
  import { fetchKbList } from '@/api/kb'
  import { DOC_SOURCE_TYPE, DOC_STATUS } from '@/constants/everkb'
  import type { ColumnOption } from '@/types/component'
  import { useTable } from '@/hooks/core/useTable'
  import { useSettingStore } from '@/store/modules/setting'

  defineOptions({ name: 'EverKBDocument' })

  const { t } = useI18n()

  type DocRow = Api.EverKB.Document

  // ── 状态机元数据（7 态着色）──────────────────────────────────────
  const STATUS_META = computed<
    Record<number, { label: string; tag: 'info' | 'primary' | 'success' | 'warning' | 'danger' }>
  >(() => ({
    [DOC_STATUS.Uploaded]: { label: t('everkb.document.statusUploaded'), tag: 'info' },
    [DOC_STATUS.Parsing]: { label: t('everkb.document.statusParsing'), tag: 'primary' },
    [DOC_STATUS.Extracted]: { label: t('everkb.document.statusExtracted'), tag: 'primary' },
    [DOC_STATUS.Chunked]: { label: t('everkb.document.statusChunked'), tag: 'primary' },
    [DOC_STATUS.Vectorizing]: { label: t('everkb.document.statusVectorizing'), tag: 'warning' },
    [DOC_STATUS.Completed]: { label: t('everkb.document.statusCompleted'), tag: 'success' },
    [DOC_STATUS.Failed]: { label: t('everkb.document.statusFailed'), tag: 'danger' }
  }))

  const isProcessing = (row: DocRow) =>
    row.status >= DOC_STATUS.Parsing && row.status <= DOC_STATUS.Vectorizing

  // ── 知识库选择 ───────────────────────────────────────────────────
  const appStore = useSettingStore()
  const kbList = ref<Api.EverKB.KB[]>([])
  const kbLoading = ref(false)
  const currentKbId = ref<number | null>(null)

  const loadKbList = async () => {
    kbLoading.value = true
    try {
      kbList.value = await fetchKbList()
      if (!currentKbId.value && kbList.value.length) {
        currentKbId.value = kbList.value[0].id
      }
    } finally {
      kbLoading.value = false
    }
  }

  // ── 表格 ─────────────────────────────────────────────────────────
  const apiFn = (params: Record<string, unknown>) => fetchDocumentPage(currentKbId.value!, params)

  const {
    data,
    loading,
    columns,
    pagination,
    fetchData,
    refreshData,
    refreshCreate,
    refreshUpdate,
    refreshRemove,
    searchParams,
    handleSizeChange,
    handleCurrentChange
  } = useTable({
    core: {
      apiFn,
      apiParams: { page: 1, size: 20 },
      paginationKey: { current: 'page' },
      immediate: false,
      columnsFactory: (): ColumnOption<DocRow>[] => [
        { prop: 'id', label: 'ID', width: 70 },
        { prop: 'name', label: t('everkb.document.colDocument'), minWidth: 260, useSlot: true },
        { prop: 'status', label: t('everkb.document.colStatus'), width: 110, useSlot: true },
        { prop: 'source_type', label: t('everkb.document.colSource'), width: 90, useSlot: true },
        { prop: 'file_type', label: t('everkb.document.colType'), width: 80 },
        {
          prop: 'file_size',
          label: t('everkb.document.colSize'),
          width: 100,
          formatter: (row) => formatSize(row.file_size)
        },
        {
          prop: 'chunk_count',
          label: t('everkb.document.colChunkCount'),
          width: 80,
          formatter: (row) => (row.chunk_count > 0 ? String(row.chunk_count) : '-')
        },
        { prop: 'enabled', label: t('everkb.document.colEnabled'), width: 80, useSlot: true },
        {
          prop: 'updated_at',
          label: t('everkb.document.colUpdatedAt'),
          width: 170,
          formatter: (row) => row.updated_at?.replace('T', ' ').slice(0, 19) || '-'
        },
        {
          prop: 'actions',
          label: t('everkb.document.colActions'),
          width: 230,
          fixed: 'right',
          useSlot: true
        }
      ]
    },
    performance: { enableCache: false }
  })

  const statusFilter = ref<number | undefined>(undefined)

  const handleKbChange = () => {
    void fetchData()
  }

  const handleStatusFilter = () => {
    searchParams.status = statusFilter.value as number | undefined
    searchParams.page = 1
    void fetchData()
  }

  const formatSize = (bytes: number) => {
    if (!bytes) return '-'
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / 1024 / 1024).toFixed(1)} MB`
  }

  // ── 自动轮询（存在处理中文档时每 5s 轻刷新）──────────────────────
  const autoRefresh = ref(true)
  let timer: ReturnType<typeof setInterval> | null = null

  onMounted(() => {
    void loadKbList().then(async () => {
      // 通知中心跳转：带 docId 时反查 kb_id 并自动选中对应知识库，直达目标文档
      const docId = route.query.docId
      if (docId) {
        try {
          const detail = await fetchDocumentDetail(Number(docId))
          if (detail.kb_id != null && kbList.value.some((kb) => kb.id === detail.kb_id)) {
            currentKbId.value = detail.kb_id
          }
        } catch {
          // 反查失败则保持默认库，不阻断列表加载
        }
      }
      if (currentKbId.value) void fetchData()
    })
    timer = setInterval(() => {
      if (!autoRefresh.value || !currentKbId.value) return
      const hasProcessing = data.value.some((row) => isProcessing(row as DocRow))
      if (hasProcessing) void fetchData()
    }, 5000)
  })

  onUnmounted(() => {
    if (timer) clearInterval(timer)
  })

  // ── 启停 / 重试 / 删除 ───────────────────────────────────────────
  const handleToggleEnabled = async (row: DocRow, enabled: boolean) => {
    try {
      const updated = await patchDocumentEnabled(row.id, enabled)
      row.enabled = updated.enabled
      ElMessage.success(
        enabled ? t('everkb.document.enableSuccess') : t('everkb.document.disableSuccess')
      )
    } catch {
      // http 层已弹错误
    }
  }

  const handleRetry = async (row: DocRow) => {
    try {
      await retryDocument(row.id)
      row.status = DOC_STATUS.Uploaded
      row.status_reason = null
      void refreshUpdate()
    } catch {
      // http 层已弹错误
    }
  }

  const handleDelete = async (row: DocRow) => {
    try {
      await ElMessageBox.confirm(
        t('everkb.document.deleteConfirm', { name: row.name }),
        t('everkb.document.deleteConfirmTitle'),
        {
          type: 'warning',
          confirmButtonText: t('everkb.document.delete'),
          cancelButtonText: t('everkb.document.cancel')
        }
      )
    } catch {
      return
    }
    try {
      await deleteDocument(row.id)
      await refreshRemove()
    } catch {
      // http 层已弹错误
    }
  }

  // ── 上传 ─────────────────────────────────────────────────────────
  const UPLOAD_LIMIT = 50
  const uploadVisible = ref(false)
  const uploading = ref(false)
  const uploadFileList = ref<UploadUserFile[]>([])

  // 每次打开弹窗先清空文件列表，避免残留上次的选择
  const openUpload = () => {
    uploadFileList.value = []
    uploadVisible.value = true
  }

  const handleUploadExceed = () => {
    ElMessage.warning(t('everkb.document.tooManyFiles'))
  }

  const handleUpload = async () => {
    const files = uploadFileList.value.map((f) => f.raw).filter((f): f is UploadRawFile => !!f)
    if (!files.length || !currentKbId.value) return
    uploading.value = true
    try {
      await uploadDocumentsBatch(currentKbId.value, files)
      uploadVisible.value = false
      uploadFileList.value = []
      await refreshCreate()
    } catch {
      // http 层已弹错误；弹窗保留，用户可剔除非法文件后重试
    } finally {
      uploading.value = false
    }
  }

  // ── 替换重传 ─────────────────────────────────────────────────────
  const replaceVisible = ref(false)
  const replacing = ref(false)
  const replacingDoc = ref<DocRow | null>(null)
  const replaceFileList = ref<UploadUserFile[]>([])

  const openReplace = (row: DocRow) => {
    replacingDoc.value = row
    replaceFileList.value = []
    replaceVisible.value = true
  }

  const handleReplace = async () => {
    const file = replaceFileList.value[0]?.raw
    if (!file || !replacingDoc.value) return
    replacing.value = true
    try {
      await replaceDocumentFile(replacingDoc.value.id, file)
      replaceVisible.value = false
      replaceFileList.value = []
      await refreshUpdate()
    } catch {
      // http 层已弹错误
    } finally {
      replacing.value = false
    }
  }

  // ── 批量添加网页 ─────────────────────────────────────────────────
  const webVisible = ref(false)
  const webSubmitting = ref(false)
  const webUrlsText = ref('')

  const webUrlList = computed(() =>
    webUrlsText.value
      .split('\n')
      .map((line) => line.trim())
      .filter(Boolean)
  )

  const openWebDialog = () => {
    webUrlsText.value = ''
    webVisible.value = true
  }

  const handleWebSubmit = async () => {
    const urls = webUrlList.value
    if (!urls.length) {
      ElMessage.warning(t('everkb.document.urlRequired'))
      return
    }
    if (urls.some((u) => !/^https?:\/\//i.test(u))) {
      ElMessage.warning(t('everkb.document.urlInvalid'))
      return
    }
    if (urls.length > 50) {
      ElMessage.warning(t('everkb.document.tooManyUrls'))
      return
    }
    webSubmitting.value = true
    try {
      await createWebDocuments(currentKbId.value!, urls)
      webVisible.value = false
      await refreshCreate()
    } catch {
      // http 层已弹错误
    } finally {
      webSubmitting.value = false
    }
  }

  // ── 原文预览 ─────────────────────────────────────────────────────
  const previewVisible = ref(false)
  const previewLoading = ref(false)
  const previewDoc = ref<DocRow | null>(null)
  const previewContent = ref('')

  const openPreview = async (row: DocRow) => {
    previewDoc.value = row
    previewVisible.value = true
    previewContent.value = ''
    previewLoading.value = true
    try {
      const res = await fetchDocumentContent(row.id)
      previewContent.value = res.content
    } catch {
      // 409/404 已由 http 层弹出
    } finally {
      previewLoading.value = false
    }
  }

  // ── 编辑器跳转 ───────────────────────────────────────────────────
  const router = useRouter()
  const route = useRoute()
  const openEditor = (row: DocRow) => {
    router.push({
      path: '/everkb/editor',
      query: { docId: String(row.id), kbId: String(currentKbId.value ?? '') }
    })
  }

  // ── chunk 浏览跳转 ───────────────────────────────────────────────
  const openChunks = (row: DocRow) => {
    router.push({
      path: '/everkb/chunk',
      query: { docId: String(row.id), kbId: String(currentKbId.value ?? '') }
    })
  }
</script>

<style lang="scss" scoped>
  .doc-page {
    padding: 16px;

    .toolbar {
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 8px;
      padding: 12px 16px;
      margin-bottom: 12px;

      .toolbar-left,
      .toolbar-right {
        display: flex;
        align-items: center;
        gap: 10px;
      }

      .toolbar-label {
        font-size: 13px;
        color: var(--art-gray-600, #888);
      }
    }

    .doc-name {
      display: flex;
      align-items: center;
      gap: 6px;
      overflow: hidden;

      .doc-name-icon {
        flex-shrink: 0;
        color: var(--art-gray-500, #aaa);
      }

      .doc-name-text {
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
        max-width: 320px;
      }
    }

    .upload-icon {
      color: var(--art-gray-500, #999);
      margin-bottom: 8px;
    }

    .replace-tip {
      margin: 0 0 12px;
      font-size: 13px;
      line-height: 1.6;
    }

    .web-count {
      margin: 8px 0 0;
      font-size: 12px;
      color: var(--art-gray-600, #888);
      text-align: right;
    }

    .preview-loading {
      min-height: 200px;
    }
  }
</style>
