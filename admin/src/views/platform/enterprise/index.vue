<template>
  <div class="platform-enterprise-page">
    <!-- 工具条：开通企业 -->
    <div class="toolbar art-card-sm">
      <div class="toolbar-left">
        <span class="toolbar-label">{{ $t('platform.enterprise.listTitle') }}</span>
      </div>
      <div class="toolbar-right">
        <ElButton type="primary" @click="openCreate">
          <el-icon style="margin-right: 4px"><Plus /></el-icon>
          {{ $t('platform.enterprise.create') }}
        </ElButton>
      </div>
    </div>

    <!-- 企业列表 -->
    <ArtTable :columns="columns" :data="data" :loading="loading" empty-height="420">
      <template #status="{ row }">
        <ElTag size="small" :type="STATUS_META[row.status]?.tag || 'info'" effect="plain">
          {{ STATUS_META[row.status]?.label || row.status }}
        </ElTag>
      </template>
      <template #actions="{ row }">
        <ElButton link type="primary" @click="openInvites(row)">
          {{ $t('platform.enterprise.invites') }}
        </ElButton>
        <ElButton link type="primary" @click="openTopup(row)">充值</ElButton>
        <ElButton
          v-if="row.status !== ENTERPRISE_STATUS.Active"
          link
          type="success"
          @click="doActivate(row)"
        >
          转正
        </ElButton>
        <ElButton
          v-if="row.status !== ENTERPRISE_STATUS.Frozen && row.status !== ENTERPRISE_STATUS.Purged"
          link
          type="warning"
          @click="openFreeze(row)"
        >
          冻结
        </ElButton>
      </template>
    </ArtTable>

    <!-- 开通企业弹窗 -->
    <ElDialog v-model="createVisible" :title="$t('platform.enterprise.create')" width="480px">
      <ElForm label-width="96px">
        <ElFormItem :label="$t('platform.enterprise.name')" required>
          <ElInput
            v-model="createForm.name"
            :placeholder="$t('platform.enterprise.namePlaceholder')"
          />
        </ElFormItem>
        <ElFormItem :label="$t('platform.enterprise.trialDays')">
          <ElInputNumber v-model="createForm.trial_days" :min="0" />
        </ElFormItem>
        <ElFormItem :label="$t('platform.enterprise.budget')">
          <ElInputNumber v-model="createForm.budget_cny" :min="0" :precision="2" :step="1" />
        </ElFormItem>
      </ElForm>
      <template #footer>
        <ElButton @click="createVisible = false">取消</ElButton>
        <ElButton type="primary" :loading="creating" @click="doCreate">确定</ElButton>
      </template>
    </ElDialog>

    <!-- 充值弹窗 -->
    <ElDialog v-model="topupVisible" :title="$t('platform.enterprise.topup')" width="420px">
      <ElForm label-width="96px">
        <ElFormItem :label="$t('platform.enterprise.enterprise')">
          <span>{{ topupTarget?.name }}</span>
        </ElFormItem>
        <ElFormItem :label="$t('platform.enterprise.amount')" required>
          <ElInputNumber v-model="topupAmount" :min="0.01" :precision="2" :step="1" />
        </ElFormItem>
      </ElForm>
      <template #footer>
        <ElButton @click="topupVisible = false">取消</ElButton>
        <ElButton type="primary" :loading="topping" @click="doTopup">确定</ElButton>
      </template>
    </ElDialog>

    <!-- 邀请码管理弹窗 -->
    <ElDialog
      v-model="inviteVisible"
      :title="`${$t('platform.enterprise.inviteListTitle')} — ${inviteTarget?.name ?? ''}`"
      width="680px"
    >
      <!-- 生成邀请码表单 -->
      <div class="invite-create">
        <div class="invite-create-row">
          <span class="invite-label">{{ $t('platform.enterprise.maxUses') }}</span>
          <ElInputNumber v-model="inviteForm.max_uses" :min="1" :max="100" />
        </div>
        <div class="invite-create-row">
          <span class="invite-label">{{ $t('platform.enterprise.note') }}</span>
          <ElInput
            v-model="inviteForm.note"
            :placeholder="$t('platform.enterprise.notePlaceholder')"
          />
        </div>
        <ElButton type="primary" :loading="creatingInvite" @click="doCreateInvite">
          <el-icon style="margin-right: 4px"><Plus /></el-icon>
          {{ $t('platform.enterprise.createInvite') }}
        </ElButton>
      </div>

      <!-- 最新生成的码高亮展示 -->
      <div v-if="lastInviteCode" class="invite-latest">
        <span class="invite-label">{{ $t('platform.enterprise.newInviteCode') }}</span>
        <code class="invite-code-text">{{ lastInviteCode }}</code>
        <ElButton size="small" @click="copyCode(lastInviteCode)">
          {{ $t('platform.enterprise.copy') }}
        </ElButton>
      </div>

      <!-- 邀请码列表 -->
      <ArtTable
        :columns="inviteColumns"
        :data="invites"
        :loading="inviteLoading"
        empty-height="200"
      >
        <template #enabled="{ row }">
          <ElTag size="small" :type="row.enabled ? 'success' : 'info'" effect="plain">
            {{
              row.enabled ? $t('platform.enterprise.enabled') : $t('platform.enterprise.disabled')
            }}
          </ElTag>
        </template>
        <template #inviteActions="{ row }">
          <ElButton v-if="row.enabled" link type="danger" @click="doDisableInvite(row)">
            {{ $t('platform.enterprise.disable') }}
          </ElButton>
        </template>
      </ArtTable>

      <div class="invite-hint">{{ $t('platform.enterprise.inviteHint') }}</div>
      <div class="invite-hint invite-hint--muted">{{
        $t('platform.enterprise.accountNotShown')
      }}</div>
    </ElDialog>
  </div>
</template>

<script setup lang="ts">
  import { Plus } from '@element-plus/icons-vue'
  import {
    activateEnterprise,
    createEnterprise,
    createInviteCode,
    disableInviteCode,
    fetchEnterpriseList,
    fetchInviteCodes,
    freezeEnterprise,
    topupEnterprise
  } from '@/api/platform'
  import { ENTERPRISE_STATUS } from '@/constants/everkb'
  import type { ColumnOption } from '@/types/component'
  import { ElMessage, ElMessageBox } from 'element-plus'

  defineOptions({ name: 'PlatformEnterprise' })

  type EnterpriseRow = Api.EverKB.Enterprise

  const STATUS_META: Record<
    number,
    { label: string; tag: 'success' | 'warning' | 'danger' | 'info' }
  > = {
    [ENTERPRISE_STATUS.Trial]: { label: '试用中', tag: 'warning' },
    [ENTERPRISE_STATUS.Active]: { label: '正式', tag: 'success' },
    [ENTERPRISE_STATUS.Frozen]: { label: '冻结', tag: 'danger' },
    [ENTERPRISE_STATUS.Purged]: { label: '已清理', tag: 'info' }
  }

  const loading = ref(false)
  const rows = ref<EnterpriseRow[]>([])

  const columns: ColumnOption<EnterpriseRow>[] = [
    { prop: 'id', label: 'ID', width: 70 },
    { prop: 'name', label: '企业名', minWidth: 140 },
    { prop: 'status', label: '状态', width: 100, useSlot: true },
    { prop: 'contact_name', label: '联系人', width: 120 },
    { prop: 'contact_way', label: '联系方式', minWidth: 140 },
    {
      prop: 'trial_ends_at',
      label: '试用截止',
      width: 160,
      formatter: (row) => (row.trial_ends_at ? row.trial_ends_at.slice(0, 10) : '—')
    },
    {
      prop: 'service_ends_at',
      label: '服务截止',
      width: 160,
      formatter: (row) => (row.service_ends_at ? row.service_ends_at.slice(0, 10) : '—')
    },
    { prop: 'actions', label: '操作', width: 220, useSlot: true, fixed: 'right' }
  ]

  const data = computed(() => rows.value)

  const load = async () => {
    loading.value = true
    try {
      rows.value = await fetchEnterpriseList()
    } catch {
      // http 层已弹错误
    } finally {
      loading.value = false
    }
  }

  // ── 开通 ──
  const createVisible = ref(false)
  const creating = ref(false)
  const createForm = reactive({ name: '', trial_days: 7, budget_cny: 20 })

  const openCreate = () => {
    createForm.name = ''
    createForm.trial_days = 7
    createForm.budget_cny = 20
    createVisible.value = true
  }

  const doCreate = async () => {
    if (!createForm.name.trim()) {
      ElMessage.warning('请输入企业名')
      return
    }
    creating.value = true
    try {
      await createEnterprise({
        name: createForm.name.trim(),
        trial_days: createForm.trial_days,
        budget_cny: createForm.budget_cny
      })
      createVisible.value = false
      await load()
    } catch {
      // http 层已弹错误
    } finally {
      creating.value = false
    }
  }

  // ── 充值 ──
  const topupVisible = ref(false)
  const topping = ref(false)
  const topupTarget = ref<EnterpriseRow | null>(null)
  const topupAmount = ref(0)

  const openTopup = (row: EnterpriseRow) => {
    topupTarget.value = row
    topupAmount.value = 0
    topupVisible.value = true
  }

  const doTopup = async () => {
    if (!topupTarget.value || topupAmount.value <= 0) {
      ElMessage.warning('请输入充值金额')
      return
    }
    topping.value = true
    try {
      await topupEnterprise(topupTarget.value.id, { amount: topupAmount.value })
      topupVisible.value = false
      await load()
    } catch {
      // http 层已弹错误
    } finally {
      topping.value = false
    }
  }

  // ── 转正 ──
  const doActivate = async (row: EnterpriseRow) => {
    try {
      await ElMessageBox.confirm(`确认将「${row.name}」转正？`, '转正', { type: 'info' })
      await activateEnterprise(row.id, { service_days: 365 })
      await load()
    } catch (e) {
      if (e === 'cancel') return
      // http 层已弹错误
    }
  }

  // ── 冻结 ──
  const openFreeze = async (row: EnterpriseRow) => {
    try {
      const { value } = await ElMessageBox.prompt(
        `确认冻结「${row.name}」？冻结后企业进入只读，60 天后数据清理。`,
        '冻结',
        {
          confirmButtonText: '冻结',
          cancelButtonText: '取消',
          inputPlaceholder: '冻结原因（可选）',
          inputValue: ''
        }
      )
      await freezeEnterprise(row.id, { reason: value || '' })
      await load()
    } catch (e) {
      if (e === 'cancel') return
      // http 层已弹错误
    }
  }

  // ── 邀请码 ──
  type InviteCodeRow = Api.EverKB.InviteCode

  const inviteVisible = ref(false)
  const inviteTarget = ref<EnterpriseRow | null>(null)
  const invites = ref<InviteCodeRow[]>([])
  const inviteLoading = ref(false)
  const creatingInvite = ref(false)
  const lastInviteCode = ref('')
  const inviteForm = reactive({ max_uses: 1, note: '' })

  const inviteColumns: ColumnOption<InviteCodeRow>[] = [
    { prop: 'code', label: '邀请码', minWidth: 180 },
    { prop: 'max_uses', label: '可用次数', width: 90 },
    { prop: 'used_count', label: '已用', width: 70 },
    { prop: 'enabled', label: '状态', width: 90, useSlot: true },
    { prop: 'note', label: '备注', minWidth: 120 },
    { prop: 'inviteActions', label: '操作', width: 80, useSlot: true }
  ]

  const openInvites = async (row: EnterpriseRow) => {
    inviteTarget.value = row
    lastInviteCode.value = ''
    inviteForm.max_uses = 1
    inviteForm.note = ''
    inviteVisible.value = true
    await loadInvites()
  }

  const loadInvites = async () => {
    if (!inviteTarget.value) return
    inviteLoading.value = true
    try {
      invites.value = await fetchInviteCodes(inviteTarget.value.id)
    } catch {
      // http 层已弹错误
    } finally {
      inviteLoading.value = false
    }
  }

  const doCreateInvite = async () => {
    if (!inviteTarget.value) return
    creatingInvite.value = true
    try {
      const inv = await createInviteCode(inviteTarget.value.id, {
        max_uses: inviteForm.max_uses,
        note: inviteForm.note.trim()
      })
      lastInviteCode.value = inv.code
      inviteForm.note = ''
      await loadInvites()
    } catch {
      // http 层已弹错误
    } finally {
      creatingInvite.value = false
    }
  }

  const doDisableInvite = async (row: InviteCodeRow) => {
    try {
      await ElMessageBox.confirm(
        '确认停用该邀请码？停用后无法再凭此码注册（已注册账号不受影响）。',
        '停用',
        {
          type: 'warning',
          confirmButtonText: '停用',
          cancelButtonText: '取消'
        }
      )
      await disableInviteCode(row.id)
      await loadInvites()
    } catch (e) {
      if (e === 'cancel') return
      // http 层已弹错误
    }
  }

  const copyCode = async (code: string) => {
    try {
      await navigator.clipboard.writeText(code)
      ElMessage.success('已复制')
    } catch {
      ElMessage.warning('复制失败，请手动复制')
    }
  }

  onMounted(() => {
    void load()
  })
</script>

<style lang="scss" scoped>
  .platform-enterprise-page {
    padding: 16px;

    .toolbar {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 12px 16px;
      margin-bottom: 12px;

      .toolbar-left,
      .toolbar-right {
        display: flex;
        align-items: center;
        gap: 10px;
      }

      .toolbar-label {
        font-size: 14px;
        font-weight: 600;
      }
    }

    .invite-create {
      display: flex;
      align-items: center;
      gap: 16px;
      padding: 12px 0;
      margin-bottom: 12px;
      border-bottom: 1px dashed var(--el-border-color);

      .invite-create-row {
        display: flex;
        align-items: center;
        gap: 8px;
      }
    }

    .invite-label {
      font-size: 13px;
      color: var(--el-text-color-secondary);
      white-space: nowrap;
    }

    .invite-latest {
      display: flex;
      align-items: center;
      gap: 12px;
      padding: 12px 16px;
      margin-bottom: 12px;
      background: var(--el-color-primary-light-9);
      border-radius: 6px;

      .invite-code-text {
        font-size: 16px;
        font-weight: 700;
        letter-spacing: 1px;
        color: var(--el-color-primary);
        font-family: 'SFMono-Regular', Consolas, monospace;
      }
    }

    .invite-hint {
      margin-top: 12px;
      font-size: 12px;
      color: var(--el-text-color-secondary);
      line-height: 1.6;

      &--muted {
        color: var(--el-text-color-placeholder);
      }
    }
  }
</style>
