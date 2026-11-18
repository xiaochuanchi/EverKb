import request from '@/utils/http'

/**
 * 文档生命周期 API（对齐后端 /api/v1/admin 文档路由）
 */

/** 库内文档分页列表（可按 status 过滤） */
export function fetchDocumentPage(kbId: number, params: Api.EverKB.DocumentPageParams = {}) {
  return request.get<Api.EverKB.DocumentPage>({
    url: `/api/v1/admin/kbs/${kbId}/documents`,
    params
  })
}

/** 文档详情 */
export function fetchDocumentDetail(docId: number) {
  return request.get<Api.EverKB.Document>({
    url: `/api/v1/admin/documents/${docId}`
  })
}

/**
 * 上传文件建文档（白名单 docx/pdf/xlsx，超限 413）
 * @param file 原始 File 对象（FormData 传输，拦截器不覆盖其 Content-Type）
 */
export function uploadDocument(kbId: number, file: File) {
  const formData = new FormData()
  formData.append('file', file)
  return request.post<Api.EverKB.Document>({
    url: `/api/v1/admin/kbs/${kbId}/documents`,
    data: formData,
    showSuccessMessage: true
  })
}

/** 批量添加网页文档（≤50/请求） */
export function createWebDocuments(kbId: number, urls: string[]) {
  return request.post<Api.EverKB.Document[]>({
    url: `/api/v1/admin/kbs/${kbId}/documents/web`,
    params: { urls },
    showSuccessMessage: true
  })
}

/** 替换重传（覆盖 source、version+1、status 置回 1；处理中/网页文档 409） */
export function replaceDocumentFile(docId: number, file: File) {
  const formData = new FormData()
  formData.append('file', file)
  return request.put<Api.EverKB.Document>({
    url: `/api/v1/admin/documents/${docId}/file`,
    data: formData,
    showSuccessMessage: true
  })
}

/** 读 content.md（status<3 时 409） */
export function fetchDocumentContent(docId: number) {
  return request.get<{ document_id: number; content: string }>({
    url: `/api/v1/admin/documents/${docId}/content`
  })
}

/** 保存编辑后的 content.md（status 置回 3，等 worker 从切块续跑） */
export function saveDocumentContent(docId: number, content: string) {
  return request.put<Api.EverKB.ContentSaveResult>({
    url: `/api/v1/admin/documents/${docId}/content`,
    params: { content },
    showSuccessMessage: true
  })
}

/** 重试失败文档（仅 status==7，其余 409） */
export function retryDocument(docId: number) {
  return request.post<Api.EverKB.Document>({
    url: `/api/v1/admin/documents/${docId}/retry`,
    showSuccessMessage: true
  })
}

/** 启停文档（Milvus 与 MySQL 同步翻转） */
export function patchDocumentEnabled(docId: number, enabled: boolean) {
  return request.request<Api.EverKB.Document>({
    url: `/api/v1/admin/documents/${docId}/enabled`,
    method: 'PATCH',
    data: { enabled },
    showSuccessMessage: false
  })
}

/** 删除文档（Milvus → chunk → doc → 存储对象；处理中 409） */
export function deleteDocument(docId: number) {
  return request.del<null>({
    url: `/api/v1/admin/documents/${docId}`,
    showSuccessMessage: true
  })
}
