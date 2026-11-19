<template>
  <div class="app-page">
    <ArtTableHeader :columns="columnChecks" :showSearchBar="false" @refresh="refreshData">
      <template #left>
        <ElButton type="primary" @click="openCreate">
          <el-icon class="mr-1"><Plus /></el-icon>
          {{ $t('everkb.app.create') }}
        </ElButton>
      </template>
    </ArtTableHeader>

    <ArtTable
      :columns="columns"
      :data="data"
      :loading="loading"
      empty-height="420"
      :emptyText="$t('everkb.app.emptyText')"
    >
      <template #kb_ids="{ row }">
        <ElTag v-if="row.kb_ids.length" type="info">{{
          $t('everkb.app.kbCount', { n: row.kb_ids.length })
        }}</ElTag>
        <span v-else>-</span>
      </template>
      <template #api_key="{ row }">
        <span class="mono muted">{{ row.api_key }}</span>
      </template>
      <template #retrieval_mode="{ row }">
        <ElTag :type="row.retrieval_mode === 'hybrid' ? 'success' : 'info'">
          {{
            row.retrieval_mode === 'hybrid'
              ? $t('everkb.app.modeHybrid')
              : $t('everkb.app.modeVector')
          }}
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
          :active-text="$t('everkb.app.enable')"
          :inactive-text="$t('everkb.app.disable')"
          @change="(v) => handleToggleStatus(row, Boolean(v))"
        />
      </template>
      <template #actions="{ row }">
        <ElButton link type="primary" @click="openEdit(row)">{{
          $t('everkb.app.editAction')
        }}</ElButton>
        <ElButton link type="primary" @click="openResetKey(row)">{{
          $t('everkb.app.resetKey')
        }}</ElButton>
        <ElButton link type="danger" @click="handleDelete(row)">{{
          $t('everkb.app.delete')
        }}</ElButton>
      </template>
    </ArtTable>

    <!-- 新建 / 编辑弹窗 -->
    <ElDialog
      v-model="dialogVisible"
      :title="editingRow ? $t('everkb.app.edit') : $t('everkb.app.create')"
      width="560px"
      :close-on-click-modal="false"
      @closed="resetForm"
    >
      <ElForm ref="formRef" :model="form" :rules="rules" label-position="top">
        <ElFormItem :label="$t('everkb.app.nameLabel')" prop="name">
          <ElInput
            v-model="form.name"
            maxlength="128"
            :placeholder="$t('everkb.app.namePlaceholder')"
          />
        </ElFormItem>
        <ElFormItem :label="$t('everkb.app.kbLabel')" prop="kb_ids">
          <ElSelect
            v-model="form.kb_ids"
            multiple
            clearable
            filterable
            :placeholder="$t('everkb.app.kbPlaceholder')"
            class="w-full"
          >
            <ElOption v-for="kb in kbOptions" :key="kb.id" :label="kb.name" :value="kb.id" />
          </ElSelect>
        </ElFormItem>
        <div class="form-grid">
          <ElFormItem label="Top K" prop="top_k">
            <ElInputNumber v-model="form.top_k" :min="1" :max="100" :step="1" class="w-full" />
          </ElFormItem>
          <ElFormItem :label="$t('everkb.app.retrievalModeLabel')" prop="retrieval_mode">
            <ElSelect v-model="form.retrieval_mode" class="w-full">
              <ElOption :label="$t('everkb.app.modeDenseOption')" value="dense" />
              <ElOption :label="$t('everkb.app.modeHybridOption')" value="hybrid" />
            </ElSelect>
          </ElFormItem>
        </div>
        <div class="form-grid">
          <ElFormItem :label="$t('everkb.app.thresholdLabel')" prop="score_threshold">
            <ElInputNumber
              v-model="form.score_threshold"
              :min="0"
              :max="1"
              :step="0.05"
              :precision="2"
              :placeholder="$t('everkb.app.thresholdPlaceholder')"
              class="w-full"
            />
          </ElFormItem>
        </div>
        <ElFormItem prop="prompt_template">
          <template #label>
            <div class="label-row">
              <span>{{ $t('everkb.app.promptLabel') }}</span>
              <ElButton link type="primary" size="small" @click="insertDefaultTemplate">
                <el-icon class="mr-1"><MagicStick /></el-icon>
                {{ $t('everkb.app.insertDefaultTpl') }}
              </ElButton>
            </div>
          </template>
          <ElInput
            v-model="form.prompt_template"
            type="textarea"
            :rows="5"
            :placeholder="$t('everkb.app.promptPlaceholder', { ctx: '{context}', q: '{question}' })"
          />
        </ElFormItem>
        <ElFormItem :label="$t('everkb.app.modelParamsLabel')" prop="model_params">
          <ElInput
            v-model="form.model_params"
            type="textarea"
            :rows="3"
            :placeholder="$t('everkb.app.modelParamsPlaceholder', { example: modelParamsExample })"
          />
        </ElFormItem>
      </ElForm>
      <template #footer>
        <ElButton @click="dialogVisible = false">{{ $t('everkb.app.cancel') }}</ElButton>
        <ElButton type="primary" :loading="submitting" @click="handleSubmit">{{
          $t('everkb.app.confirm')
        }}</ElButton>
      </template>
    </ElDialog>

    <!-- 明文 api_key 展示弹窗（创建 / 重置后仅此一次） -->
    <ElDialog
      v-model="keyDialogVisible"
      :title="$t('everkb.app.apiKeyTitle')"
      width="520px"
      :close-on-click-modal="false"
      :show-close="false"
    >
      <ElAlert
        type="warning"
        :closable="false"
        class="mb-3"
        :title="$t('everkb.app.apiKeyWarning')"
      />
      <div class="key-box">
        <code class="mono">{{ plainApiKey }}</code>
        <ElButton link type="primary" @click="copyKey">
          <el-icon class="mr-1"><CopyDocument /></el-icon>
          {{ $t('everkb.app.copy') }}
        </ElButton>
      </div>
      <template #footer>
        <ElButton type="primary" @click="keyDialogVisible = false">{{
          $t('everkb.app.saved')
        }}</ElButton>
      </template>
    </ElDialog>
  </div>
</template>

<script setup lang="ts">
  import { ElMessage, ElMessageBox, type FormInstance, type FormRules } from 'element-plus'
  import { CopyDocument, MagicStick, Plus } from '@element-plus/icons-vue'
  import { useI18n } from 'vue-i18n'
  import { createApp, deleteApp, fetchAppList, resetAppKey, updateApp } from '@/api/everkb/app'
  import { fetchKbList } from '@/api/kb'
  import type { ColumnOption } from '@/types/component'
  import { useTable } from '@/hooks/core/useTable'

  defineOptions({ name: 'EverKBApp' })

  const { t } = useI18n()

  const modelParamsExample = '{"model": "..."}'

  // 与后端系统默认模板保持一致（backend/app/services/rag.py DEFAULT_PROMPT_TEMPLATE），改模板需两边同步
  const DEFAULT_PROMPT_TEMPLATE = [
    '你是一个知识库问答助手。请仅根据以下参考资料回答用户问题，并在引用资料时标注编号（如 [1]）。如果参考资料不足以回答，请如实说明。',
    '',
    '参考资料：',
    '{context}',
    '',
    '用户问题：{question}'
  ].join('\n')

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
        { prop: 'name', label: t('everkb.app.nameLabel'), minWidth: 160 },
        { prop: 'kb_ids', label: t('everkb.app.kbColumn'), width: 110, useSlot: true },
        { prop: 'top_k', label: 'Top K', width: 90 },
        {
          prop: 'retrieval_mode',
          label: t('everkb.app.retrievalModeLabel'),
          width: 100,
          useSlot: true
        },
        {
          prop: 'score_threshold',
          label: t('everkb.app.thresholdColumn'),
          width: 90,
          useSlot: true
        },
        { prop: 'api_key', label: 'API Key', minWidth: 160, useSlot: true },
        { prop: 'enabled', label: t('everkb.app.statusLabel'), width: 100, useSlot: true },
        {
          prop: 'updated_at',
          label: t('everkb.app.updatedAt'),
          width: 170,
          formatter: (row) => row.updated_at?.replace('T', ' ').slice(0, 19) || '-'
        },
        {
          prop: 'actions',
          label: t('everkb.app.actions'),
          width: 200,
          fixed: 'right',
          useSlot: true
        }
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
      ElMessage.success(enabled ? t('everkb.app.enabledMsg') : t('everkb.app.disabledMsg'))
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
      { required: true, message: t('everkb.app.nameRequired'), trigger: 'blur' },
      { min: 1, max: 128, message: t('everkb.app.lengthLimit'), trigger: 'blur' }
    ],
    prompt_template: [
      {
        // 与后端 schemas.py 校验一致：非空模板必须含 {question}，否则问题无法注入
        validator: (_rule, value: string, callback) => {
          if (!value || !value.trim()) return callback()
          if (!value.includes('{question}')) {
            callback(new Error(t('everkb.app.promptQuestionRequired', { q: '{question}' })))
          } else {
            callback()
          }
        },
        trigger: 'blur'
      }
    ],
    model_params: [
      {
        validator: (_rule, value: string, callback) => {
          if (!value || !value.trim()) return callback()
          try {
            const obj = JSON.parse(value)
            if (typeof obj !== 'object' || Array.isArray(obj) || obj === null) {
              callback(new Error(t('everkb.app.jsonObjectError', { example: '{"model": "..."}' })))
            } else {
              callback()
            }
          } catch {
            callback(new Error(t('everkb.app.jsonFormatError')))
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

  // ── Prompt 模板辅助 ──────────────────────────────────────────────
  /** 插入系统默认模板；已有内容时先确认覆盖 */
  const insertDefaultTemplate = async () => {
    if (form.prompt_template.trim()) {
      try {
        await ElMessageBox.confirm(
          t('everkb.app.tplOverwriteConfirm'),
          t('everkb.app.tplOverwriteTitle'),
          {
            type: 'warning',
            confirmButtonText: t('everkb.app.confirm'),
            cancelButtonText: t('everkb.app.cancel')
          }
        )
      } catch {
        return
      }
    }
    form.prompt_template = DEFAULT_PROMPT_TEMPLATE
    formRef.value?.clearValidate('prompt_template')
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
      ElMessage.error(t('everkb.app.modelParamsJsonError'))
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
      ElMessage.success(t('everkb.app.copied'))
    } catch {
      ElMessage.error(t('everkb.app.copyFailed'))
    }
  }

  // ── 重置密钥 ─────────────────────────────────────────────────────
  const openResetKey = async (row: AppRow) => {
    try {
      await ElMessageBox.confirm(
        t('everkb.app.resetKeyConfirm', { name: row.name }),
        t('everkb.app.resetKeyTitle'),
        {
          type: 'warning',
          confirmButtonText: t('everkb.app.reset'),
          cancelButtonText: t('everkb.app.cancel')
        }
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
      await ElMessageBox.confirm(
        t('everkb.app.deleteConfirm', { name: row.name }),
        t('everkb.app.deleteTitle'),
        {
          type: 'warning',
          confirmButtonText: t('everkb.app.delete'),
          cancelButtonText: t('everkb.app.cancel')
        }
      )
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

  .label-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    width: 100%;
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
