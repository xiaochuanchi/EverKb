import request from '@/utils/http'

/**
 * EverKB Chunk 浏览 API（对齐后端 /api/v1/admin/documents/{id}/chunks，Task 13）
 * chunk 由 content.md 切分而来，双存 MySQL 与 Milvus（id 兼作 Milvus 主键）。
 */

/** 单文档 chunk 分页列表（按 chunk_index 升序） */
export function fetchChunkPage(documentId: number, params: Api.EverKB.ChunkPageParams = {}) {
  return request.get<Api.EverKB.ChunkPage>({
    url: `/api/v1/admin/documents/${documentId}/chunks`,
    params
  })
}
