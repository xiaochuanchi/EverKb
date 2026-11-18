import request from '@/utils/http'

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
 * 获取当前登录账号信息（GET /api/v1/admin/auth/me）
 *
 * 后端只回 {id, username, is_active, created_at}；此处映射为模板 UserInfo
 * 结构供 store/路由守卫消费。单管理员后台，roles 固定 R_SUPER。
 */
export async function fetchGetUserInfo() {
  const me = await request.get<Api.Auth.MeResponse>({
    url: '/api/v1/admin/auth/me'
  })
  const userInfo: Api.Auth.UserInfo = {
    userId: me.id,
    userName: me.username,
    roles: ['R_SUPER'],
    buttons: [],
    email: ''
  }
  return userInfo
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
