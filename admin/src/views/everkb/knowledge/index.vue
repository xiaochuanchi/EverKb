<template>
  <div class="kb-page">
    <ArtTableHeader :columns="columnChecks" :showSearchBar="false" @refresh="refreshData">
      <template #left>
        <ElButton type="primary" @click="openCreate">
          <el-icon class="mr-1"><Plus /></el-icon>
          新建知识库
        </ElButton>
      </template>
    </ArtTableHeader>

    <ArtTable
      :columns="columns"
      :data="data"
      :loading="loading"
      empty-height="420"
      emptyText="还没有知识库，点击「新建知识库」创建第一个"
    >
      <template #status="{ row }">
        <ElSwitch
          :model-value="row.status === KB_STATUS.Enabled"
          :loading="row._statusLoading"
          :inline-prompt="true"
          active-text="启用"
          inactive-text="停用"
          @change="(v) => handleToggleStatus(row, Boolean(v))"
        />
      </template>
      <template #actions="{ row }">
        <ElButton link type="primary" @click="openEdit(row)">编辑</ElButton>
        <ElButton link type="danger" @click="handleDelete(row)">删除</ElButton>
      </template>
    </ArtTable>

    <!-- 新建 / 编辑弹窗 -->
    <ElDialog
      v-model="dialogVisible"
      :title="editingRow ? '编辑知识库' : '新建知识库'"
      width="480px"
      :close-on-click-modal="false"
      @closed="resetForm"
    >
      <ElForm ref="formRef" :model="form" :rules="rules" label-position="top">
        <ElFormItem label="名称" prop="name">
          <ElInput v-model="form.name" maxlength="128" placeholder="知识库名称（唯一）" />
        </ElFormItem>
        <ElFormItem label="描述" prop="description">
          <ElInput
            v-model="form.description"
            type="textarea"
            :rows="3"
            maxlength="512"
            show-word-limit
            placeholder="简要说明该知识库的用途（可选）"
          />
        </ElFormItem>
      </ElForm>
      <template #footer>
        <ElButton @click="dialogVisible = false">取消</ElButton>
        <ElButton type="primary" :loading="submitting" @click="handleSubmit">确定</ElButton>
      </template>
    </ElDialog>
  </div>
</template>

<script setup lang="ts">
  import { ElMessage, ElMessageBox, type FormInstance, type FormRules } from 'element-plus'
  import { Plus } from '@element-plus/icons-vue'
  import { createKb, deleteKb, fetchKbList, updateKb } from '@/api/kb'
  import { KB_STATUS } from '@/constants/everkb'
  import type { ColumnOption } from '@/types/component'
  import { useTable } from '@/hooks/core/useTable'

  defineOptions({ name: 'EverKBKnowledge' })

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
        { prop: 'name', label: '名称', minWidth: 180 },
        {
          prop: 'description',
          label: '描述',
          minWidth: 220,
          showOverflowTooltip: true,
          formatter: (row) => row.description || '-'
        },
        { prop: 'status', label: '状态', width: 110, useSlot: true },
        {
          prop: 'created_at',
          label: '创建时间',
          width: 170,
          formatter: (row) => row.created_at?.replace('T', ' ').slice(0, 19) || '-'
        },
        { prop: 'actions', label: '操作', width: 140, fixed: 'right', useSlot: true }
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
      ElMessage.success(enabled ? '已启用' : '已停用')
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
      { required: true, message: '请输入知识库名称', trigger: 'blur' },
      { min: 1, max: 128, message: '长度 1 ~ 128 位', trigger: 'blur' }
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
      await ElMessageBox.confirm(`确定删除知识库「${row.name}」吗？仅空库可删除。`, '删除确认', {
        type: 'warning',
        confirmButtonText: '删除',
        cancelButtonText: '取消'
      })
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
