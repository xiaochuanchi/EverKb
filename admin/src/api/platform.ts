import request from '@/utils/http'

/**
 * 平台运营后台 API（对齐后端 /api/v1/platform/*，M5）
 * 仅平台管理员（R_PLATFORM）可访问；企业列表/开通/转正/冻结/充值/钱包。
 */

/** 企业列表（GET /platform/enterprises） */
export function fetchEnterpriseList() {
  return request.get<Api.EverKB.Enterprise[]>({
    url: '/api/v1/platform/enterprises'
  })
}

/** 开通企业（试用，POST /platform/enterprises） */
export function createEnterprise(data: Api.EverKB.EnterpriseCreateParams) {
  return request.post<Api.EverKB.Enterprise>({
    url: '/api/v1/platform/enterprises',
    data,
    showSuccessMessage: true
  })
}

/** 转正（POST /platform/enterprises/{id}/activate） */
export function activateEnterprise(id: number, data: Api.EverKB.EnterpriseActivateParams) {
  return request.post<Api.EverKB.Enterprise>({
    url: `/api/v1/platform/enterprises/${id}/activate`,
    data,
    showSuccessMessage: true
  })
}

/** 冻结（POST /platform/enterprises/{id}/freeze） */
export function freezeEnterprise(id: number, data: Api.EverKB.EnterpriseFreezeParams) {
  return request.post<Api.EverKB.Enterprise>({
    url: `/api/v1/platform/enterprises/${id}/freeze`,
    data,
    showSuccessMessage: true
  })
}

/** 充值（POST /platform/enterprises/{id}/topup，累加预算） */
export function topupEnterprise(id: number, data: Api.EverKB.EnterpriseTopupParams) {
  return request.post<Api.EverKB.Wallet>({
    url: `/api/v1/platform/enterprises/${id}/topup`,
    data,
    showSuccessMessage: true
  })
}

/** 企业钱包余额（GET /platform/enterprises/{id}/wallet） */
export function fetchEnterpriseWallet(id: number) {
  return request.get<Api.EverKB.Wallet>({
    url: `/api/v1/platform/enterprises/${id}/wallet`
  })
}

/* ============ 企业管理员注册码（M5 补） ============ */

/** 为企业发企业管理员注册码（POST /platform/enterprises/{id}/invites） */
export function createInviteCode(id: number, data: Api.EverKB.InviteCodeCreateParams) {
  return request.post<Api.EverKB.InviteCode>({
    url: `/api/v1/platform/enterprises/${id}/invites`,
    data,
    showSuccessMessage: true
  })
}

/** 企业注册码列表（GET /platform/enterprises/{id}/invites） */
export function fetchInviteCodes(id: number) {
  return request.get<Api.EverKB.InviteCode[]>({
    url: `/api/v1/platform/enterprises/${id}/invites`
  })
}

/** 停用注册码（POST /platform/invites/{id}/disable） */
export function disableInviteCode(inviteId: number) {
  return request.post<Api.EverKB.InviteCode>({
    url: `/api/v1/platform/invites/${inviteId}/disable`,
    showSuccessMessage: true
  })
}
