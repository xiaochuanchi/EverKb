<template>
  <div class="wallet-page">
    <div class="balance-card art-card">
      <div class="card-header">
        <span class="card-title">{{ $t('everkb.wallet.balanceTitle') }}</span>
      </div>
      <div class="balance-grid">
        <div class="balance-item balance-primary">
          <div class="balance-label">{{ $t('everkb.wallet.remaining') }}</div>
          <div class="balance-value">¥{{ formatCny(wallet.remaining_cny) }}</div>
        </div>
        <div class="balance-item">
          <div class="balance-label">{{ $t('everkb.wallet.budget') }}</div>
          <div class="balance-value">¥{{ formatCny(wallet.budget_cny) }}</div>
        </div>
        <div class="balance-item">
          <div class="balance-label">{{ $t('everkb.wallet.spent') }}</div>
          <div class="balance-value">¥{{ formatCny(wallet.spent_cny) }}</div>
        </div>
        <div class="balance-item">
          <div class="balance-label">{{ $t('everkb.wallet.reserved') }}</div>
          <div class="balance-value">¥{{ formatCny(wallet.reserved_cny) }}</div>
        </div>
      </div>
      <div class="refresh-bar">
        <ElButton :loading="loading" @click="load">
          <el-icon style="margin-right: 4px"><Refresh /></el-icon>
          {{ $t('everkb.wallet.refresh') }}
        </ElButton>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
  import { Refresh } from '@element-plus/icons-vue'
  import { fetchWallet } from '@/api/everkb/wallet'

  defineOptions({ name: 'EverKBWallet' })

  const loading = ref(false)
  const wallet = ref<Api.EverKB.Wallet>({
    enterprise_id: 0,
    budget_cny: 0,
    spent_cny: 0,
    reserved_cny: 0,
    remaining_cny: 0
  })

  const formatCny = (v: number) => (Number(v) || 0).toFixed(2)

  const load = async () => {
    loading.value = true
    try {
      wallet.value = await fetchWallet()
    } catch {
      // http 层已弹错误
    } finally {
      loading.value = false
    }
  }

  onMounted(() => {
    void load()
  })
</script>

<style lang="scss" scoped>
  .wallet-page {
    padding: 16px;

    .balance-card {
      max-width: 720px;

      .card-header {
        margin-bottom: 8px;

        .card-title {
          font-weight: 600;
        }
      }

      .balance-grid {
        display: grid;
        grid-template-columns: repeat(2, 1fr);
        gap: 16px;
        padding: 8px 0 16px;

        .balance-item {
          padding: 16px;
          border-radius: 8px;
          background: var(--art-fill-color-lighter, #f5f7fa);

          .balance-label {
            font-size: 13px;
            color: var(--art-text-color-secondary, #888);
            margin-bottom: 8px;
          }

          .balance-value {
            font-size: 22px;
            font-weight: 600;
          }

          &.balance-primary {
            background: var(--art-color-primary-light-9, #ecf5ff);

            .balance-value {
              color: var(--art-color-primary, #409eff);
              font-size: 28px;
            }
          }
        }
      }

      .refresh-bar {
        display: flex;
        justify-content: flex-end;
      }
    }
  }
</style>
