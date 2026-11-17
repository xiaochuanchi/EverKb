import request from '@/utils/http'

/**
 * EverKB 应用管理 API
 * 应用 = 产品侧机器人/场景，挂载知识库检索
 */

/** 应用列表 */
export function fetchAppList() {
  return request.get<Api.EverKB.App[]>({
    url: '/api/apps'
  })
}

/** 创建应用 */
export function fetchCreateApp(params: Api.EverKB.AppCreateParams) {
  return request.post<Api.EverKB.App>({
    url: '/api/apps',
    params
  })
}

/** 更新应用（挂载知识库、top_k/阈值/Prompt/模型参数） */
export function fetchUpdateApp(params: Api.EverKB.AppUpdateParams) {
  return request.put<Api.EverKB.App>({
    url: `/api/apps/${params.id}`,
    params
  })
}

/** 删除应用 */
export function fetchDeleteApp(id: number) {
  return request.del<void>({
    url: `/api/apps/${id}`
  })
}
