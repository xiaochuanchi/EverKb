import request from '@/utils/http'

/**
 * 企业钱包 API（对齐后端 /api/v1/admin/wallet，M2 后端 / M5 前端页）
 * 企业管理员查看本企业钱包余额（全员共享）。
 */

/** 当前企业钱包余额（GET /admin/wallet） */
export function fetchWallet() {
  return request.get<Api.EverKB.Wallet>({
    url: '/api/v1/admin/wallet'
  })
}
