import request from '@/utils/http'
import { useUserStore } from '@/store/modules/user'

/**
 * 登录（POST /api/v1/admin/auth/login）
 * @param params 登录参数
 * @returns 后端 TokenOut：{access_token, token_type}（单 access JWT，无 refresh）
 */
export function fetchLogin(params: Api.Auth.LoginParams) {
  return request.post<Api.Auth.LoginResponse>({
    url: '/api/v1/admin/auth/login',
    params
  })
}

/**
 * 凭邀请码注册体验账号（POST /api/v1/admin/auth/register）
 * 注册成功即返回 token，前端可直接置为登录态。
 */
export function fetchRegister(params: Api.Auth.RegisterParams) {
  return request.post<Api.Auth.RegisterResponse>({
    url: '/api/v1/admin/auth/register',
    params
  })
}

/**
 * 获取当前登录账号信息（GET /api/v1/admin/auth/me）
 *
 * 后端回真实 role（platform/ent_admin/member）与 enterprise_id；此处按角色映射
 * 前端角色码（M5 商业化多租户角色分流）：
 *   platform   → R_PLATFORM（运营工作台）
 *   ent_admin  → R_ENT_ADMIN（企业控制台）
 *   member     → R_MEMBER（预留，随成员账号体系后移）
 * 菜单按 meta.roles 过滤，三套世界互不串门。
 */
export async function fetchGetUserInfo() {
  const me = await request.get<Api.Auth.MeResponse>({
    url: '/api/v1/admin/auth/me'
  })
  const roleMap: Record<string, string> = {
    platform: 'R_PLATFORM',
    ent_admin: 'R_ENT_ADMIN',
    member: 'R_MEMBER'
  }
  const userInfo: Api.Auth.UserInfo = {
    userId: me.id,
    userName: me.username,
    roles: [roleMap[me.role] || 'R_MEMBER'],
    buttons: [],
    email: '',
    role: me.role,
    enterpriseId: me.enterprise_id
  }
  return userInfo
}

/** 刷新当前账号信息（问答扣费后更新额度展示） */
export async function refreshUserInfo() {
  const info = await fetchGetUserInfo()
  useUserStore().setUserInfo(info)
  return info
}

/**
 * 修改密码（PUT /api/v1/admin/auth/password）
 *
 * 后端无黑名单期旧 token 仍有效至过期（≤24h）；成功后前端主动登出重登。
 */
export function fetchChangePassword(params: { old_password: string; new_password: string }) {
  return request.put<null>({
    url: '/api/v1/admin/auth/password',
    data: params
  })
}
