import request from '@/utils/http'

/**
 * EverKB 应用管理 API（对齐后端 /api/v1/admin/apps，Task 18）
 * 应用 = 产品侧问答入口（挂知识库 + 检索参数 + 模型配置）。
 * api_key 仅在「创建」和「重置」两个时机明文返回，其余读取一律脱敏（sk-***）。
 */

/** 应用列表（api_key 已脱敏） */
export function fetchAppList() {
  return request.get<Api.EverKB.App[]>({
    url: '/api/v1/admin/apps'
  })
}

/** 创建应用（api_key 唯一一次明文返回） */
export function createApp(data: Api.EverKB.AppCreateParams) {
  return request.post<Api.EverKB.AppCreateResult>({
    url: '/api/v1/admin/apps',
    data,
    showSuccessMessage: true
  })
}

/** 局部更新（name/kb_ids/top_k/score_threshold/prompt_template/model_params/enabled） */
export function updateApp(id: number, data: Api.EverKB.AppPatchParams) {
  return request.request<Api.EverKB.App>({
    url: `/api/v1/admin/apps/${id}`,
    method: 'PATCH',
    data,
    showSuccessMessage: true
  })
}

/** 删除应用 */
export function deleteApp(id: number) {
  return request.del<null>({
    url: `/api/v1/admin/apps/${id}`,
    showSuccessMessage: true
  })
}

/** 重置 api_key（返回新明文，旧 key 即刻失效） */
export function resetAppKey(id: number) {
  return request.post<Api.EverKB.AppKeyResult>({
    url: `/api/v1/admin/apps/${id}/reset-key`,
    showSuccessMessage: true
  })
}
