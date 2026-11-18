<template>
  <div class="doc-page">
    <!-- 工具条：知识库选择 + 状态过滤 + 上传/网页/刷新 -->
    <div class="toolbar art-card-sm">
      <div class="toolbar-left">
        <span class="toolbar-label">知识库</span>
        <ElSelect
          v-model="currentKbId"
          :loading="kbLoading"
          placeholder="选择知识库"
          style="width: 220px"
          @change="handleKbChange"
        >
          <ElOption v-for="kb in kbList" :key="kb.id" :label="kb.name" :value="kb.id" />
        </ElSelect>

        <span class="toolbar-label">状态</span>
        <ElSelect
          v-model="statusFilter"
          placeholder="全部"
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

        <ElTooltip content="有处理中的文档时每 5 秒自动刷新" placement="top">
          <ElSwitch v-model="autoRefresh" inline-prompt active-text="自动" inactive-text="手动" />
        </ElTooltip>
      </div>

      <div class="toolbar-right">
        <ElButton type="primary" :disabled="!currentKbId" @click="uploadVisible = true">
          <el-icon class="mr-1"><Upload /></el-icon>
          上传文档
        </ElButton>
        <ElButton :disabled="!currentKbId" @click="openWebDialog">
          <el-icon class="mr-1"><Link /></el-icon>
          添加网页
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
      :emptyText="currentKbId ? '该库暂无文档' : '请先选择知识库'"
      @pagination:size-change="handleSizeChange"
      @pagination:current-change="handleCurrentChange"
    >
      <template #name="{ row }">
        <div class="doc-name">
          <el-icon class="doc-name-icon"><Document /></el-icon>
          <span class="doc-name-text" :title="row.name">{{ row.name }}</span>
          <ElTag v-if="row.edited" size="small" type="warning" effect="plain">已编辑</ElTag>
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
          {{ STATUS_META[row.status]?.label || `未知(${row.status})` }}
        </ElTag>
      </template>

      <template #source_type="{ row }">
        <ElTag size="small" effect="plain" :type="row.source_type === DOC_SOURCE_TYPE.Webpage ? 'success' : 'info'">
          {{ row.source_type === DOC_SOURCE_TYPE.Webpage ? '网页' : '上传' }}
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
          编辑
        </ElButton>
        <ElButton
          v-if="row.source_type === DOC_SOURCE_TYPE.Upload && !isProcessing(row)"
          link
          type="primary"
          @click="openReplace(row)"
        >
          替换
        </ElButton>
        <ElButton
          v-if="row.status === DOC_STATUS.Failed"
          link
          type="warning"
          @click="handleRetry(row)"
        >
          重试
        </ElButton>
        <ElButton link type="primary" @click="openPreview(row)">预览</ElButton>
        <ElButton
          v-if="row.status >= DOC_STATUS.Extracted"
          link
          type="primary"
          @click="openChunks(row)"
        >
          块
        </ElButton>
        <ElButton v-if="!isProcessing(row)" link type="danger" @click="handleDelete(row)">
          删除
        </ElButton>
      </template>
    </ArtTable>

    <!-- 上传文档弹窗 -->
    <ElDialog v-model="uploadVisible" title="上传文档" width="480px" :close-on-click-modal="false">
      <ElUpload
        drag
        :auto-upload="false"
        :limit="1"
        :on-change="handleFileChange"
        :on-remove="() => (uploadFile = null)"
        accept=".docx,.pdf,.xlsx,.txt,.md,.csv,.html"
      >
        <el-icon :size="40" class="upload-icon"><UploadFilled /></el-icon>
        <div class="el-upload__text">拖拽文件到此处，或 <em>点击选择</em></div>
        <template #tip>
          <div class="el-upload__tip">支持 docx / pdf / xlsx / txt / md / csv / html，单文件不超过 10MB</div>
        </template>
      </ElUpload>
      <template #footer>
        <ElButton @click="uploadVisible = false">取消</ElButton>
        <ElButton type="primary" :loading="uploading" :disabled="!uploadFile" @click="handleUpload">
          上传
        </ElButton>
      </template>
    </ElDialog>

    <!-- 替换重传弹窗 -->
    <ElDialog v-model="replaceVisible" title="替换文件" width="480px" :close-on-click-modal="false">
      <p class="replace-tip">
        覆盖 <b>{{ replacingDoc?.name }}</b> 的源文件，版本 +1 并重新处理；处理期间旧版内容持续供检索。
      </p>
      <ElUpload
        drag
        :auto-upload="false"
        :limit="1"
        :on-change="handleReplaceFileChange"
        :on-remove="() => (replaceFile = null)"
        accept=".docx,.pdf,.xlsx,.txt,.md,.csv,.html"
      >
        <el-icon :size="40" class="upload-icon"><UploadFilled /></el-icon>
        <div class="el-upload__text">拖拽新文件到此处，或 <em>点击选择</em></div>
        <template #tip>
          <div class="el-upload__tip">支持 docx / pdf / xlsx / txt / md / csv / html，单文件不超过 10MB</div>
        </template>
      </ElUpload>
      <template #footer>
        <ElButton @click="replaceVisible = false">取消</ElButton>
        <ElButton type="primary" :loading="replacing" :disabled="!replaceFile" @click="handleReplace">
          替换
        </ElButton>
      </template>
    </ElDialog>

    <!-- 批量添加网页弹窗 -->
    <ElDialog v-model="webVisible" title="批量添加网页" width="560px" :close-on-click-modal="false">
      <ElInput
        v-model="webUrlsText"
        type="textarea"
        :rows="8"
        placeholder="每行一个 URL（http/https），一次最多 50 条"
      />
      <p class="web-count">已输入 {{ webUrlList.length }} 条</p>
      <template #footer>
        <ElButton @click="webVisible = false">取消</ElButton>
        <ElButton type="primary" :loading="webSubmitting" @click="handleWebSubmit">提交</ElButton>
      </template>
    </ElDialog>

    <!-- 原文预览抽屉 -->
    <ElDrawer v-model="previewVisible" :title="previewDoc?.name || '原文预览'" size="60%">
      <div v-if="previewLoading" class="preview-loading" v-loading="true" :element-loading-text="'加载中'" />
      <MdPreview v-else-if="previewContent" :model-value="previewContent" :theme="appStore.isDark ? 'dark' : 'light'" />
      <ElEmpty v-else description="暂无 markdown 内容" />
    </ElDrawer>
  </div>
</template>

<script setup lang="ts">
  import { ElMessage, ElMessageBox } from 'element-plus'
  import { Document, Link, Refresh, Upload, UploadFilled } from '@element-plus/icons-vue'
  import { MdPreview } from 'md-editor-v3'
  import 'md-editor-v3/lib/style.css'
  import {
    createWebDocuments,
    deleteDocument,
    fetchDocumentContent,
    fetchDocumentPage,
    patchDocumentEnabled,
    replaceDocumentFile,
    retryDocument,
    uploadDocument
  } from '@/api/document'
  import { fetchKbList } from '@/api/kb'
  import { DOC_SOURCE_TYPE, DOC_STATUS } from '@/constants/everkb'
  import type { ColumnOption } from '@/types/component'
  import { useTable } from '@/hooks/core/useTable'
  import { useSettingStore } from '@/store/modules/setting'

  defineOptions({ name: 'EverKBDocument' })

  type DocRow = Api.EverKB.Document

  // ── 状态机元数据（7 态着色）──────────────────────────────────────
  const STATUS_META: Record<number, { label: string; tag: 'info' | 'primary' | 'success' | 'warning' | 'danger' }> = {
    [DOC_STATUS.Uploaded]: { label: '已上传', tag: 'info' },
    [DOC_STATUS.Parsing]: { label: '解析中', tag: 'primary' },
    [DOC_STATUS.Extracted]: { label: '已抽取', tag: 'primary' },
    [DOC_STATUS.Chunked]: { label: '已切块', tag: 'primary' },
    [DOC_STATUS.Vectorizing]: { label: '向量化中', tag: 'warning' },
    [DOC_STATUS.Completed]: { label: '已完成', tag: 'success' },
    [DOC_STATUS.Failed]: { label: '失败', tag: 'danger' }
  }

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
  const apiFn = (params: Record<string, unknown>) =>
    fetchDocumentPage(currentKbId.value!, params)

  const { data, loading, columns, pagination, fetchData, refreshData, refreshCreate, refreshUpdate, refreshRemove, searchParams, handleSizeChange, handleCurrentChange } =
    useTable({
      core: {
        apiFn,
        apiParams: { page: 1, size: 20 },
        paginationKey: { current: 'page' },
        immediate: false,
        columnsFactory: (): ColumnOption<DocRow>[] => [
          { prop: 'id', label: 'ID', width: 70 },
          { prop: 'name', label: '文档', minWidth: 260, useSlot: true },
          { prop: 'status', label: '状态', width: 110, useSlot: true },
          { prop: 'source_type', label: '来源', width: 90, useSlot: true },
          { prop: 'file_type', label: '类型', width: 80 },
          {
            prop: 'file_size',
            label: '大小',
            width: 100,
            formatter: (row) => formatSize(row.file_size)
          },
          {
            prop: 'chunk_count',
            label: '块数',
            width: 80,
            formatter: (row) => (row.chunk_count > 0 ? String(row.chunk_count) : '-')
          },
          { prop: 'enabled', label: '启用', width: 80, useSlot: true },
          {
            prop: 'updated_at',
            label: '更新时间',
            width: 170,
            formatter: (row) => row.updated_at?.replace('T', ' ').slice(0, 19) || '-'
          },
          { prop: 'actions', label: '操作', width: 230, fixed: 'right', useSlot: true }
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
    void loadKbList().then(() => {
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
      ElMessage.success(enabled ? '已启用' : '已停用')
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
        `确定删除文档「${row.name}」吗？其 chunk 与向量将一并清理。`,
        '删除确认',
        { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' }
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
  const uploadVisible = ref(false)
  const uploading = ref(false)
  const uploadFile = ref<File | null>(null)

  const handleFileChange = (file: { raw?: File }) => {
    uploadFile.value = file.raw ?? null
  }

  const handleUpload = async () => {
    if (!uploadFile.value || !currentKbId.value) return
    uploading.value = true
    try {
      await uploadDocument(currentKbId.value, uploadFile.value)
      uploadVisible.value = false
      uploadFile.value = null
      await refreshCreate()
    } catch {
      // http 层已弹错误
    } finally {
      uploading.value = false
    }
  }

  // ── 替换重传 ─────────────────────────────────────────────────────
  const replaceVisible = ref(false)
  const replacing = ref(false)
  const replacingDoc = ref<DocRow | null>(null)
  const replaceFile = ref<File | null>(null)

  const openReplace = (row: DocRow) => {
    replacingDoc.value = row
    replaceFile.value = null
    replaceVisible.value = true
  }

  const handleReplaceFileChange = (file: { raw?: File }) => {
    replaceFile.value = file.raw ?? null
  }

  const handleReplace = async () => {
    if (!replaceFile.value || !replacingDoc.value) return
    replacing.value = true
    try {
      await replaceDocumentFile(replacingDoc.value.id, replaceFile.value)
      replaceVisible.value = false
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
      ElMessage.warning('请至少输入一个 URL')
      return
    }
    if (urls.some((u) => !/^https?:\/\//i.test(u))) {
      ElMessage.warning('存在非法 URL，须以 http:// 或 https:// 开头')
      return
    }
    if (urls.length > 50) {
      ElMessage.warning('单次最多 50 条')
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
  const openEditor = (row: DocRow) => {
    router.push({ path: '/everkb/editor', query: { docId: String(row.id), kbId: String(currentKbId.value ?? '') } })
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
