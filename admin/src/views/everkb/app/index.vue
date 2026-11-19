<template>
  <div class="app-page">
    <ArtTableHeader :columns="columnChecks" :showSearchBar="false" @refresh="refreshData">
      <template #left>
        <ElButton type="primary" @click="openCreate">
          <el-icon class="mr-1"><Plus /></el-icon>
          新建应用
        </ElButton>
      </template>
    </ArtTableHeader>

    <ArtTable
      :columns="columns"
      :data="data"
      :loading="loading"
      empty-height="420"
      emptyText="还没有应用，点击「新建应用」创建第一个问答入口"
    >
      <template #kb_ids="{ row }">
        <ElTag v-if="row.kb_ids.length" type="info">{{ row.kb_ids.length }} 个库</ElTag>
        <span v-else>-</span>
      </template>
      <template #api_key="{ row }">
        <span class="mono muted">{{ row.api_key }}</span>
      </template>
      <template #retrieval_mode="{ row }">
        <ElTag :type="row.retrieval_mode === 'hybrid' ? 'success' : 'info'">
          {{ row.retrieval_mode === 'hybrid' ? '混合' : '向量' }}
        </ElTag>
      </template>
      <template #score_threshold="{ row }">
        <span>{{ row.score_threshold == null ? '-' : row.score_threshold }}</span>
      </template>
      <template #enabled="{ row }">
        <ElSwitch
          :model-value="row.enabled"
          :loading="row._statusLoading"
          :inline-prompt="true"
          active-text="启用"
          inactive-text="停用"
          @change="(v) => handleToggleStatus(row, Boolean(v))"
        />
      </template>
      <template #actions="{ row }">
        <ElButton link type="primary" @click="openEdit(row)">编辑</ElButton>
        <ElButton link type="primary" @click="openResetKey(row)">重置密钥</ElButton>
        <ElButton link type="danger" @click="handleDelete(row)">删除</ElButton>
      </template>
    </ArtTable>

    <!-- 新建 / 编辑弹窗 -->
    <ElDialog
      v-model="dialogVisible"
      :title="editingRow ? '编辑应用' : '新建应用'"
      width="560px"
      :close-on-click-modal="false"
      @closed="resetForm"
    >
      <ElForm ref="formRef" :model="form" :rules="rules" label-position="top">
        <ElFormItem label="名称" prop="name">
          <ElInput
            v-model="form.name"
            maxlength="128"
            placeholder="应用名称（唯一），如「客服助手」"
          />
        </ElFormItem>
        <ElFormItem label="挂载知识库" prop="kb_ids">
          <ElSelect
            v-model="form.kb_ids"
            multiple
            clearable
            filterable
            placeholder="选择可检索的知识库（可多选，留空则不检索）"
            class="w-full"
          >
            <ElOption v-for="kb in kbOptions" :key="kb.id" :label="kb.name" :value="kb.id" />
          </ElSelect>
        </ElFormItem>
        <div class="form-grid">
          <ElFormItem label="Top K" prop="top_k">
            <ElInputNumber v-model="form.top_k" :min="1" :max="100" :step="1" class="w-full" />
          </ElFormItem>
          <ElFormItem label="检索模式" prop="retrieval_mode">
            <ElSelect v-model="form.retrieval_mode" class="w-full">
              <ElOption label="纯向量（语义）" value="dense" />
              <ElOption label="混合检索（语义 + 关键词）" value="hybrid" />
            </ElSelect>
          </ElFormItem>
        </div>
        <div class="form-grid">
          <ElFormItem label="相似度阈值" prop="score_threshold">
            <ElInputNumber
              v-model="form.score_threshold"
              :min="0"
              :max="1"
              :step="0.05"
              :precision="2"
              placeholder="留空不限"
              class="w-full"
            />
          </ElFormItem>
        </div>
        <ElFormItem label="Prompt 模板" prop="prompt_template">
          <ElInput
            v-model="form.prompt_template"
            type="textarea"
            :rows="3"
            placeholder="留空使用系统默认模板（占位符 {context} / {question}）"
          />
        </ElFormItem>
        <ElFormItem label="模型参数（JSON）" prop="model_params">
          <ElInput
            v-model="form.model_params"
            type="textarea"
            :rows="3"
            placeholder='可选，如 {"model": "doubao-seed-2-0-lite-260428"}'
          />
        </ElFormItem>
      </ElForm>
      <template #footer>
        <ElButton @click="dialogVisible = false">取消</ElButton>
        <ElButton type="primary" :loading="submitting" @click="handleSubmit">确定</ElButton>
      </template>
    </ElDialog>

    <!-- 明文 api_key 展示弹窗（创建 / 重置后仅此一次） -->
    <ElDialog
      v-model="keyDialogVisible"
      title="API Key（仅显示这一次，请妥善保存）"
      width="520px"
      :close-on-click-modal="false"
      :show-close="false"
    >
      <ElAlert type="warning" :closable="false" class="mb-3" title="关闭后无法再次查看明文密钥" />
      <div class="key-box">
        <code class="mono">{{ plainApiKey }}</code>
        <ElButton link type="primary" @click="copyKey">
          <el-icon class="mr-1"><CopyDocument /></el-icon>
          复制
        </ElButton>
      </div>
      <template #footer>
        <ElButton type="primary" @click="keyDialogVisible = false">我已保存</ElButton>
      </template>
    </ElDialog>
  </div>
</template>

<script setup lang="ts">
  import { ElMessage, ElMessageBox, type FormInstance, type FormRules } from 'element-plus'
  import { CopyDocument, Plus } from '@element-plus/icons-vue'
  import { createApp, deleteApp, fetchAppList, resetAppKey, updateApp } from '@/api/everkb/app'
  import { fetchKbList } from '@/api/kb'
  import type { ColumnOption } from '@/types/component'
  import { useTable } from '@/hooks/core/useTable'

  defineOptions({ name: 'EverKBApp' })

  type AppRow = Api.EverKB.App & { _statusLoading?: boolean }

  /** 列表加载：后端不分页，返回全量数组 */
  const apiFn = () => fetchAppList()

  const {
    data,
    loading,
    columns,
    columnChecks,
    fetchData,
    refreshData,
    refreshCreate,
    refreshUpdate,
    refreshRemove
  } = useTable({
    core: {
      apiFn,
      immediate: true,
      columnsFactory: (): ColumnOption<AppRow>[] => [
        { prop: 'id', label: 'ID', width: 70 },
        { prop: 'name', label: '名称', minWidth: 160 },
        { prop: 'kb_ids', label: '挂载库', width: 110, useSlot: true },
        { prop: 'top_k', label: 'Top K', width: 90 },
        { prop: 'retrieval_mode', label: '检索模式', width: 100, useSlot: true },
        { prop: 'score_threshold', label: '阈值', width: 90, useSlot: true },
        { prop: 'api_key', label: 'API Key', minWidth: 160, useSlot: true },
        { prop: 'enabled', label: '状态', width: 100, useSlot: true },
        {
          prop: 'updated_at',
          label: '更新时间',
          width: 170,
          formatter: (row) => row.updated_at?.replace('T', ' ').slice(0, 19) || '-'
        },
        { prop: 'actions', label: '操作', width: 200, fixed: 'right', useSlot: true }
      ]
    },
    performance: { enableCache: false }
  })

  // ── 知识库选项（挂载多选）─────────────────────────────────────
  const kbOptions = ref<Api.EverKB.KB[]>([])
  const loadKbOptions = async () => {
    try {
      kbOptions.value = await fetchKbList()
    } catch {
      // 错误已由 http 层弹出
    }
  }

  // ── 状态启停 ─────────────────────────────────────────────────────
  const handleToggleStatus = async (row: AppRow, enabled: boolean) => {
    row._statusLoading = true
    try {
      await updateApp(row.id, { enabled })
      row.enabled = enabled
      ElMessage.success(enabled ? '已启用' : '已停用')
    } catch {
      // 失败静默（http 层已弹错误）
    } finally {
      row._statusLoading = false
    }
  }

  // ── 新建 / 编辑 ──────────────────────────────────────────────────
  const dialogVisible = ref(false)
  const submitting = ref(false)
  const editingRow = ref<AppRow | null>(null)
  const formRef = ref<FormInstance>()
  const form = reactive({
    name: '',
    kb_ids: [] as number[],
    top_k: 5,
    retrieval_mode: 'dense' as 'dense' | 'hybrid',
    score_threshold: null as number | null,
    prompt_template: '',
    model_params: ''
  })

  const rules: FormRules = {
    name: [
      { required: true, message: '请输入应用名称', trigger: 'blur' },
      { min: 1, max: 128, message: '长度 1 ~ 128 位', trigger: 'blur' }
    ],
    model_params: [
      {
        validator: (_rule, value: string, callback) => {
          if (!value || !value.trim()) return callback()
          try {
            const obj = JSON.parse(value)
            if (typeof obj !== 'object' || Array.isArray(obj) || obj === null) {
              callback(new Error('需为 JSON 对象，如 {"model": "..."}'))
            } else {
              callback()
            }
          } catch {
            callback(new Error('JSON 格式错误'))
          }
        },
        trigger: 'blur'
      }
    ]
  }

  const openCreate = () => {
    editingRow.value = null
    dialogVisible.value = true
    void loadKbOptions()
  }

  const openEdit = (row: AppRow) => {
    editingRow.value = row
    form.name = row.name
    form.kb_ids = [...row.kb_ids]
    form.top_k = row.top_k
    form.retrieval_mode = row.retrieval_mode || 'dense'
    form.score_threshold = row.score_threshold
    form.prompt_template = row.prompt_template || ''
    form.model_params =
      row.model_params && Object.keys(row.model_params).length
        ? JSON.stringify(row.model_params, null, 2)
        : ''
    dialogVisible.value = true
    void loadKbOptions()
  }

  const resetForm = () => {
    form.name = ''
    form.kb_ids = []
    form.top_k = 5
    form.retrieval_mode = 'dense'
    form.score_threshold = null
    form.prompt_template = ''
    form.model_params = ''
    editingRow.value = null
    formRef.value?.resetFields()
  }

  const parseModelParams = (): Record<string, unknown> | undefined => {
    const raw = form.model_params.trim()
    if (!raw) return undefined
    return JSON.parse(raw) as Record<string, unknown>
  }

  const handleSubmit = async () => {
    try {
      await formRef.value?.validate()
    } catch {
      return
    }
    let modelParams: Record<string, unknown> | undefined
    try {
      modelParams = parseModelParams()
    } catch {
      ElMessage.error('模型参数 JSON 格式错误')
      return
    }
    submitting.value = true
    try {
      if (editingRow.value) {
        await updateApp(editingRow.value.id, {
          name: form.name,
          kb_ids: form.kb_ids,
          top_k: form.top_k,
          retrieval_mode: form.retrieval_mode,
          score_threshold: form.score_threshold ?? undefined,
          prompt_template: form.prompt_template || undefined,
          model_params: modelParams
        })
        await refreshUpdate()
      } else {
        const created = await createApp({
          name: form.name,
          kb_ids: form.kb_ids,
          top_k: form.top_k,
          retrieval_mode: form.retrieval_mode,
          score_threshold: form.score_threshold ?? undefined,
          prompt_template: form.prompt_template || undefined,
          model_params: modelParams
        })
        await refreshCreate()
        showPlainKey(created.api_key)
      }
      dialogVisible.value = false
    } catch {
      // 错误消息已由 http 层弹出（重名 409 等）
    } finally {
      submitting.value = false
    }
  }

  // ── 明文 key 展示 + 复制 ────────────────────────────────────────
  const keyDialogVisible = ref(false)
  const plainApiKey = ref('')

  const showPlainKey = (key: string) => {
    plainApiKey.value = key
    keyDialogVisible.value = true
  }

  const copyKey = async () => {
    try {
      await navigator.clipboard.writeText(plainApiKey.value)
      ElMessage.success('已复制到剪贴板')
    } catch {
      ElMessage.error('复制失败，请手动复制')
    }
  }

  // ── 重置密钥 ─────────────────────────────────────────────────────
  const openResetKey = async (row: AppRow) => {
    try {
      await ElMessageBox.confirm(
        `确定重置应用「${row.name}」的 API Key 吗？旧密钥将立即失效。`,
        '重置密钥确认',
        { type: 'warning', confirmButtonText: '重置', cancelButtonText: '取消' }
      )
    } catch {
      return
    }
    try {
      const result = await resetAppKey(row.id)
      showPlainKey(result.api_key)
    } catch {
      // 错误已由 http 层弹出
    }
  }

  // ── 删除 ─────────────────────────────────────────────────────────
  const handleDelete = async (row: AppRow) => {
    try {
      await ElMessageBox.confirm(`确定删除应用「${row.name}」吗？`, '删除确认', {
        type: 'warning',
        confirmButtonText: '删除',
        cancelButtonText: '取消'
      })
    } catch {
      return
    }
    try {
      await deleteApp(row.id)
      await refreshRemove()
    } catch {
      // 错误已由 http 层弹出
    }
  }

  onMounted(() => {
    void fetchData()
  })
</script>

<style lang="scss" scoped>
  .app-page {
    padding: 16px;
  }

  .form-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 12px;
  }

  .w-full {
    width: 100%;
  }

  .mono {
    font-family: var(--art-font-mono, ui-monospace, 'SF Mono', Menlo, Consolas, monospace);
  }

  .muted {
    color: var(--art-text-color-secondary, #909399);
    font-size: 13px;
  }

  .key-box {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    padding: 12px 14px;
    background: var(--art-fill-color-light, #f5f7fa);
    border-radius: 6px;

    code {
      word-break: break-all;
      font-size: 14px;
    }
  }
</style>
