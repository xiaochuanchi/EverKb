<template>
  <div class="user-center-page">
    <!-- 左侧：账号信息卡 -->
    <div class="info-card">
      <div class="avatar-wrap">
        <el-icon :size="42" class="avatar-icon"><User /></el-icon>
      </div>
      <h2 class="username">{{ userInfo.userName || '-' }}</h2>
      <el-tag v-if="meInfo?.is_active" type="success" size="small">正常</el-tag>
      <el-tag v-else type="danger" size="small">已禁用</el-tag>

      <div class="meta-list">
        <div class="meta-item">
          <span class="meta-label">账号 ID</span>
          <span class="meta-value">{{ meInfo?.id ?? '-' }}</span>
        </div>
        <div class="meta-item">
          <span class="meta-label">创建时间</span>
          <span class="meta-value">{{ formatTime(meInfo?.created_at) }}</span>
        </div>
        <div class="meta-item">
          <span class="meta-label">当前版本</span>
          <span class="meta-value">v{{ appVersion }}</span>
        </div>
      </div>
    </div>

    <!-- 右侧：修改密码 -->
    <div class="pwd-card">
      <h3 class="card-title">修改密码</h3>
      <p class="card-tip">修改成功后将退出登录，请使用新密码重新登录。</p>

      <ElForm
        ref="formRef"
        :model="form"
        :rules="rules"
        label-position="top"
        class="pwd-form"
        @keyup.enter="handleSubmit"
      >
        <ElFormItem label="当前密码" prop="old_password">
          <ElInput
            v-model="form.old_password"
            type="password"
            show-password
            placeholder="请输入当前密码"
          />
        </ElFormItem>
        <ElFormItem label="新密码" prop="new_password">
          <ElInput
            v-model="form.new_password"
            type="password"
            show-password
            placeholder="至少 8 位，最长 64 位"
          />
        </ElFormItem>
        <ElFormItem label="确认新密码" prop="confirm">
          <ElInput
            v-model="form.confirm"
            type="password"
            show-password
            placeholder="再次输入新密码"
          />
        </ElFormItem>
        <ElFormItem>
          <ElButton type="primary" :loading="submitting" @click="handleSubmit">确认修改</ElButton>
          <ElButton @click="handleReset">重置</ElButton>
        </ElFormItem>
      </ElForm>
    </div>
  </div>
</template>

<script setup lang="ts">
  import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
  import { User } from '@element-plus/icons-vue'
  import request from '@/utils/http'
  import { fetchChangePassword } from '@/api/auth'
  import { useUserStore } from '@/store/modules/user'

  defineOptions({ name: 'UserCenter' })

  /** 产品版本号（vite define 注入；模板直用全局常量过不了 vue-tsc） */
  const appVersion = __APP_VERSION__

  const userStore = useUserStore()
  const router = useRouter()
  const formRef = ref<FormInstance>()
  const submitting = ref(false)

  /** 顶栏展示用的映射信息 */
  const userInfo = computed(() => userStore.getUserInfo)

  /** /auth/me 原始信息（id/is_active/created_at） */
  const meInfo = ref<Api.Auth.MeResponse | null>(null)

  const fetchMeRaw = () => request.get<Api.Auth.MeResponse>({ url: '/api/v1/admin/auth/me' })

  onMounted(async () => {
    try {
      meInfo.value = await fetchMeRaw()
    } catch {
      // me 请求失败不打断页面（store 里的 userName 仍可展示）
    }
  })

  const form = reactive({
    old_password: '',
    new_password: '',
    confirm: ''
  })

  const rules: FormRules = {
    old_password: [{ required: true, message: '请输入当前密码', trigger: 'blur' }],
    new_password: [
      { required: true, message: '请输入新密码', trigger: 'blur' },
      { min: 8, max: 64, message: '长度 8 ~ 64 位', trigger: 'blur' },
      {
        validator: (_rule, value, callback) => {
          if (value && value === form.old_password) {
            callback(new Error('新密码不能与当前密码相同'))
          } else {
            callback()
          }
        },
        trigger: 'blur'
      }
    ],
    confirm: [
      { required: true, message: '请再次输入新密码', trigger: 'blur' },
      {
        validator: (_rule, value, callback) => {
          if (value && value !== form.new_password) {
            callback(new Error('两次输入的密码不一致'))
          } else {
            callback()
          }
        },
        trigger: 'blur'
      }
    ]
  }

  const formatTime = (iso?: string) => (iso ? iso.replace('T', ' ').slice(0, 19) : '-')

  const handleSubmit = async () => {
    try {
      await formRef.value?.validate()
    } catch {
      return
    }
    submitting.value = true
    try {
      await fetchChangePassword({
        old_password: form.old_password,
        new_password: form.new_password
      })
      ElMessage.success('密码修改成功，即将跳转登录页')
      // 后端旧 token 有效至过期，但统一 UX：改密即重登
      setTimeout(() => {
        userStore.logOut()
        router.push('/login')
      }, 800)
    } finally {
      submitting.value = false
    }
  }

  const handleReset = () => {
    formRef.value?.resetFields()
  }
</script>

<style lang="scss" scoped>
  .user-center-page {
    display: flex;
    gap: 16px;
    padding: 16px;
    align-items: flex-start;

    .info-card,
    .pwd-card {
      background: var(--art-main-bg-color);
      border-radius: 8px;
      padding: 24px;
    }

    .info-card {
      width: 280px;
      flex-shrink: 0;
      text-align: center;

      .avatar-wrap {
        width: 72px;
        height: 72px;
        margin: 0 auto 12px;
        border-radius: 50%;
        background: var(--art-bg-color, rgba(53, 95, 233, 0.1));
        color: var(--art-main-color, #355fe9);
        display: flex;
        align-items: center;
        justify-content: center;
      }

      .username {
        margin: 0 0 8px;
        font-size: 18px;
        font-weight: 500;
      }

      .meta-list {
        margin-top: 20px;
        text-align: left;

        .meta-item {
          display: flex;
          justify-content: space-between;
          padding: 8px 0;
          border-bottom: 1px dashed rgba(0, 0, 0, 0.08);
          font-size: 13px;

          .meta-label {
            color: var(--art-gray-600, #888);
          }
        }
      }
    }

    .pwd-card {
      flex: 1;
      max-width: 520px;

      .card-title {
        margin: 0 0 4px;
        font-size: 16px;
        font-weight: 500;
      }

      .card-tip {
        margin: 0 0 16px;
        font-size: 12px;
        color: var(--art-gray-600, #888);
      }

      .pwd-form {
        max-width: 360px;
      }
    }
  }
</style>
