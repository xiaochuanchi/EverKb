<template>
  <div class="kb-page">
    <ArtTableHeader :columns="columnChecks" :showSearchBar="false" @refresh="refreshData">
      <template #left>
        <ElButton type="primary" @click="openCreate">
          <el-icon class="mr-1"><Plus /></el-icon>
          {{ $t('everkb.knowledge.create') }}
        </ElButton>
      </template>
    </ArtTableHeader>

    <ArtTable
      :columns="columns"
      :data="data"
      :loading="loading"
      empty-height="420"
      :emptyText="$t('everkb.knowledge.emptyText')"
    >
      <template #status="{ row }">
        <ElSwitch
          :model-value="row.status === KB_STATUS.Enabled"
          :loading="row._statusLoading"
          :inline-prompt="true"
          :active-text="$t('everkb.knowledge.enable')"
          :inactive-text="$t('everkb.knowledge.disable')"
          @change="(v) => handleToggleStatus(row, Boolean(v))"
        />
      </template>
      <template #actions="{ row }">
        <ElButton link type="primary" @click="openEdit(row)">{{
          $t('everkb.knowledge.edit')
        }}</ElButton>
        <ElButton link type="danger" @click="handleDelete(row)">{{
          $t('everkb.knowledge.delete')
        }}</ElButton>
      </template>
    </ArtTable>

    <!-- 新建 / 编辑弹窗 -->
    <ElDialog
      v-model="dialogVisible"
      :title="editingRow ? $t('everkb.knowledge.editTitle') : $t('everkb.knowledge.create')"
      width="480px"
      :close-on-click-modal="false"
      @closed="resetForm"
    >
      <ElForm ref="formRef" :model="form" :rules="rules" label-position="top">
        <ElFormItem :label="$t('everkb.knowledge.nameLabel')" prop="name">
          <ElInput
            v-model="form.name"
            maxlength="128"
            :placeholder="$t('everkb.knowledge.namePlaceholder')"
          />
        </ElFormItem>
        <ElFormItem :label="$t('everkb.knowledge.descLabel')" prop="description">
          <ElInput
            v-model="form.description"
            type="textarea"
            :rows="3"
            maxlength="512"
            show-word-limit
            :placeholder="$t('everkb.knowledge.descPlaceholder')"
          />
        </ElFormItem>
      </ElForm>
      <template #footer>
        <ElButton @click="dialogVisible = false">{{ $t('everkb.knowledge.cancel') }}</ElButton>
        <ElButton type="primary" :loading="submitting" @click="handleSubmit">{{
          $t('everkb.knowledge.confirm')
        }}</ElButton>
      </template>
    </ElDialog>
  </div>
</template>

<script setup lang="ts">
  import { ElMessage, ElMessageBox, type FormInstance, type FormRules } from 'element-plus'
  import { useI18n } from 'vue-i18n'
  import { Plus } from '@element-plus/icons-vue'
  import { createKb, deleteKb, fetchKbList, updateKb } from '@/api/kb'
  import { KB_STATUS } from '@/constants/everkb'
  import type { ColumnOption } from '@/types/component'
  import { useTable } from '@/hooks/core/useTable'

  defineOptions({ name: 'EverKBKnowledge' })

  const { t } = useI18n()

  type KBRow = Api.EverKB.KB & { _statusLoading?: boolean }

  /** 列表加载：后端不分页，返回全量数组（useTable 数组响应自动适配） */
  const apiFn = () => fetchKbList()

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
      columnsFactory: (): ColumnOption<KBRow>[] => [
        { prop: 'id', label: 'ID', width: 70 },
        { prop: 'name', label: t('everkb.knowledge.nameLabel'), minWidth: 180 },
        {
          prop: 'description',
          label: t('everkb.knowledge.descLabel'),
          minWidth: 220,
          showOverflowTooltip: true,
          formatter: (row) => row.description || '-'
        },
        { prop: 'status', label: t('everkb.knowledge.status'), width: 110, useSlot: true },
        {
          prop: 'created_at',
          label: t('everkb.knowledge.createdAt'),
          width: 170,
          formatter: (row) => row.created_at?.replace('T', ' ').slice(0, 19) || '-'
        },
        {
          prop: 'actions',
          label: t('everkb.knowledge.actions'),
          width: 140,
          fixed: 'right',
          useSlot: true
        }
      ]
    },
    performance: { enableCache: false }
  })

  // ── 状态启停 ─────────────────────────────────────────────────────
  const handleToggleStatus = async (row: KBRow, enabled: boolean) => {
    row._statusLoading = true
    try {
      await updateKb(row.id, {
        status: enabled ? KB_STATUS.Enabled : KB_STATUS.Disabled
      })
      row.status = enabled ? KB_STATUS.Enabled : KB_STATUS.Disabled
      ElMessage.success(enabled ? t('everkb.knowledge.enabled') : t('everkb.knowledge.disabled'))
    } catch {
      // 失败静默（http 层已弹错误消息），开关状态由 model-value 回退
    } finally {
      row._statusLoading = false
    }
  }

  // ── 新建 / 编辑 ──────────────────────────────────────────────────
  const dialogVisible = ref(false)
  const submitting = ref(false)
  const editingRow = ref<KBRow | null>(null)
  const formRef = ref<FormInstance>()
  const form = reactive({ name: '', description: '' })

  const rules: FormRules = {
    name: [
      { required: true, message: t('everkb.knowledge.nameRequired'), trigger: 'blur' },
      { min: 1, max: 128, message: t('everkb.knowledge.lengthRange'), trigger: 'blur' }
    ]
  }

  const openCreate = () => {
    editingRow.value = null
    dialogVisible.value = true
  }

  const openEdit = (row: KBRow) => {
    editingRow.value = row
    form.name = row.name
    form.description = row.description
    dialogVisible.value = true
  }

  const resetForm = () => {
    form.name = ''
    form.description = ''
    editingRow.value = null
    formRef.value?.resetFields()
  }

  const handleSubmit = async () => {
    try {
      await formRef.value?.validate()
    } catch {
      return
    }
    submitting.value = true
    try {
      if (editingRow.value) {
        await updateKb(editingRow.value.id, {
          name: form.name,
          description: form.description
        })
        await refreshUpdate()
      } else {
        await createKb({ name: form.name, description: form.description })
        await refreshCreate()
      }
      dialogVisible.value = false
    } catch {
      // 错误消息已由 http 层弹出（重名 409 等），弹窗保持打开供修改
    } finally {
      submitting.value = false
    }
  }

  // ── 删除 ─────────────────────────────────────────────────────────
  const handleDelete = async (row: KBRow) => {
    try {
      await ElMessageBox.confirm(
        t('everkb.knowledge.deleteConfirm', { name: row.name }),
        t('everkb.knowledge.deleteConfirmTitle'),
        {
          type: 'warning',
          confirmButtonText: t('everkb.knowledge.delete'),
          cancelButtonText: t('everkb.knowledge.cancel')
        }
      )
    } catch {
      return
    }
    try {
      await deleteKb(row.id)
      await refreshRemove()
    } catch {
      // 409「库内仍有文档」等已由 http 层弹出
    }
  }

  onMounted(() => {
    void fetchData()
  })
</script>

<style lang="scss" scoped>
  .kb-page {
    padding: 16px;
  }
</style>
