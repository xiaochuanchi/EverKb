/**
 * API 接口类型定义模块
 *
 * 提供所有后端接口的类型定义
 *
 * ## 主要功能
 *
 * - 通用类型（分页参数、响应结构等）
 * - 认证类型（登录、用户信息等）
 * - 系统管理类型（用户、角色等）
 * - 全局命名空间声明
 *
 * ## 使用场景
 *
 * - API 请求参数类型约束
 * - API 响应数据类型定义
 * - 接口文档类型同步
 *
 * ## 注意事项
 *
 * - 在 .vue 文件使用需要在 eslint.config.mjs 中配置 globals: { Api: 'readonly' }
 * - 使用全局命名空间，无需导入即可使用
 *
 * ## 使用方式
 *
 * ```typescript
 * const params: Api.Auth.LoginParams = { username: 'admin', password: 'your-password' }
 * const response: Api.Auth.UserInfo = await fetchUserInfo()
 * ```
 *
 * @module types/api/api
 * @author Art Design Pro Team
 */

declare namespace Api {
  /** 通用类型 */
  namespace Common {
    /** 分页参数 */
    interface PaginationParams {
      /** 当前页码 */
      current: number
      /** 每页条数 */
      size: number
      /** 总条数 */
      total: number
    }

    /** 通用搜索参数 */
    type CommonSearchParams = Pick<PaginationParams, 'current' | 'size'>

    /** 分页响应基础结构 */
    interface PaginatedResponse<T = any> {
      records: T[]
      current: number
      size: number
      total: number
    }

    /** 启用状态 */
    type EnableStatus = '1' | '2'
  }

  /** 认证类型（对齐 EverKB 后端 /api/v1/admin/auth） */
  namespace Auth {
    /** 登录参数（POST /auth/login） */
    interface LoginParams {
      username: string
      password: string
    }

    /** 登录响应（后端 TokenOut：单 access JWT，无 refresh） */
    interface LoginResponse {
      access_token: string
      token_type: string
    }

    /** GET /auth/me 原始响应 */
    interface MeResponse {
      id: number
      username: string
      is_active: boolean
      created_at: string
    }

    /** 用户信息（由 api 层从 MeResponse 映射，供模板 store/守卫消费） */
    interface UserInfo {
      buttons: string[]
      roles: string[]
      userId: number
      userName: string
      email: string
      avatar?: string
    }
  }

  /** EverKB 业务类型（对齐后端 /api/v1/admin 契约，见 backend/app/schemas.py）
   *  枚举的运行时值在 src/constants/everkb.ts（declare enum 无运行时值，勿在此声明） */
  namespace EverKB {
    /** 知识库状态（models.KBStatus）：0=停用 1=启用，运行时值 KB_STATUS */
    /** 知识库（后端 KBOut） */
    interface KB {
      id: number
      name: string
      description: string
      status: number
      created_at: string
    }

    /** POST /kbs 请求体 */
    interface KBCreateParams {
      name: string
      description?: string
    }

    /** PATCH /kbs/{id} 请求体（未传字段不修改） */
    interface KBPatchParams {
      name?: string
      description?: string
      status?: number
    }

    /** 文档状态机（models.DocumentStatus）：1→2→3→4→5→6，任一环节失败→7；运行时值 DOC_STATUS */

    /** 文档来源（models.SourceType）：1=上传 2=网页，运行时值 DOC_SOURCE_TYPE */

    /** 文档（后端 DocumentOut） */
    interface Document {
      id: number
      kb_id: number
      name: string
      source_type: number
      source_url: string | null
      file_type: string
      file_size: number
      status: number
      status_reason: string | null
      version: number
      enabled: boolean
      chunk_count: number
      edited: boolean
      uploaded_by: string
      created_at: string
      updated_at: string
    }

    /** GET /kbs/{kbId}/documents 分页响应（后端 DocumentPageOut） */
    interface DocumentPage {
      total: number
      page: number
      size: number
      items: Document[]
    }

    /** 文档分页查询参数 */
    interface DocumentPageParams {
      page?: number
      size?: number
      status?: number
    }

    /** 批量添加网页请求体 */
    interface WebDocParams {
      urls: string[]
    }

    /** PUT /documents/{id}/content 保存后的文档（DocumentOut 同 Document） */
    type ContentSaveResult = Document

    /** GET /documents/{id}/content 响应体 */
    interface DocumentContent {
      document_id: number
      content: string
    }

    /* ============ Chunk（Task 13） ============ */

    /** chunk（后端 ChunkOut） */
    interface Chunk {
      id: number
      chunk_index: number
      page_number: number | null
      content: string
      token_count: number
      vectorized: boolean
    }

    /** GET /documents/{id}/chunks 分页响应（后端 ChunkPageOut） */
    interface ChunkPage {
      total: number
      page: number
      size: number
      items: Chunk[]
    }

    /** chunk 分页查询参数 */
    interface ChunkPageParams {
      page?: number
      size?: number
    }

    /* ============ 应用管理（Task 18） ============ */

    /** 应用（后端 AppOut，api_key 已脱敏为 sk-***） */
    interface App {
      id: number
      name: string
      kb_ids: number[]
      api_key: string
      enabled: boolean
      top_k: number
      score_threshold: number | null
      prompt_template: string | null
      model_params: Record<string, unknown>
      created_at: string
      updated_at: string
    }

    /** 创建应用响应（后端 AppCreateOut，api_key 唯一一次明文返回） */
    type AppCreateResult = App

    /** POST /apps 请求体 */
    interface AppCreateParams {
      name: string
      kb_ids?: number[]
      top_k?: number
      score_threshold?: number
      prompt_template?: string
      model_params?: Record<string, unknown>
    }

    /** PATCH /apps/{id} 请求体（未传字段不修改） */
    interface AppPatchParams {
      name?: string
      kb_ids?: number[]
      top_k?: number
      score_threshold?: number
      prompt_template?: string
      model_params?: Record<string, unknown>
      enabled?: boolean
    }

    /** POST /apps/{id}/reset-key 响应（后端 AppKeyOut） */
    interface AppKeyResult {
      api_key: string
    }

    /* ============ 问答记录（Task 22） ============ */

    /** 引用详情（citations 单元素，后端 build_context 下发） */
    interface Citation {
      doc_name: string
      doc_id: number
      chunk_id: number
      page_number: number | null
      snippet: string
      score: number
      source_url: string | null
    }

    /** 问答记录（后端 QaRecordOut） */
    interface QaRecord {
      id: number
      app_id: number
      user_key: string
      session_id: string | null
      question: string
      answer: string
      grounded: boolean
      chunk_ids: number[]
      doc_ids: number[]
      scores: number[]
      citations: Citation[]
      model_snapshot: Record<string, unknown>
      latency_ms: number
      total_cost: number | null
      feedback: number
      created_at: string
    }

    /** GET /records 分页响应（后端 QaRecordPageOut） */
    interface QaRecordPage {
      total: number
      page: number
      size: number
      items: QaRecord[]
    }

    /** 问答记录分页查询参数 */
    interface QaRecordPageParams {
      app_id?: number
      feedback?: number
      page?: number
      size?: number
    }

    /* ============ Trace 查看（Task 22） ============ */

    /** span 树节点（后端 TraceSpanNode，children 递归成树） */
    interface TraceSpanNode {
      id: number
      name: string
      span_type: string
      parent_span_id: number | null
      input_summary: string | null
      output_summary: string | null
      start_time: string
      end_time: string
      latency_ms: number
      gen_ai_usage_tokens_in: number | null
      gen_ai_usage_tokens_out: number | null
      cost: number | null
      extra: Record<string, unknown> | null
      children: TraceSpanNode[]
    }

    /** GET /traces/{record_id} 响应（后端 TraceTreeOut） */
    interface TraceTree {
      record_id: number
      spans: TraceSpanNode[]
    }

    /** span（后端 TraceSpanOut，聚合 slowest 列表用） */
    interface TraceSpan {
      id: number
      trace_id: number
      parent_span_id: number | null
      name: string
      span_type: string
      input_summary: string | null
      output_summary: string | null
      start_time: string
      end_time: string
      latency_ms: number
      gen_ai_usage_tokens_in: number | null
      gen_ai_usage_tokens_out: number | null
      cost: number | null
      extra: Record<string, unknown> | null
    }

    /** 单 span_type 聚合指标（后端 SpanAggregateItem） */
    interface SpanAggregateItem {
      span_type: string
      count: number
      p95_latency_ms: number | null
      avg_tokens_in: number | null
      avg_tokens_out: number | null
      avg_cost: number | null
    }

    /** GET /traces/aggregate 响应（后端 TraceAggregateOut） */
    interface TraceAggregation {
      slowest: TraceSpan[]
      by_type: SpanAggregateItem[]
    }

    /* ============ 对账工具（Task 13） ============ */

    /** GET /reconciliation 单条漂移项（后端 ReconciliationItemOut） */
    interface ReconciliationItem {
      doc_id: number
      issue: string
    }
  }

  /** 系统管理类型 */
  namespace SystemManage {
    /** 用户列表 */
    type UserList = Api.Common.PaginatedResponse<UserListItem>

    /** 用户列表项 */
    interface UserListItem {
      id: number
      avatar: string
      status: string
      userName: string
      userGender: string
      nickName: string
      userPhone: string
      userEmail: string
      userRoles: string[]
      createBy: string
      createTime: string
      updateBy: string
      updateTime: string
    }

    /** 用户搜索参数 */
    type UserSearchParams = Partial<
      Pick<UserListItem, 'id' | 'userName' | 'userGender' | 'userPhone' | 'userEmail' | 'status'> &
        Api.Common.CommonSearchParams
    >

    /** 角色列表 */
    type RoleList = Api.Common.PaginatedResponse<RoleListItem>

    /** 角色列表项 */
    interface RoleListItem {
      roleId: number
      roleName: string
      roleCode: string
      description: string
      enabled: boolean
      createTime: string
    }

    /** 角色搜索参数 */
    type RoleSearchParams = Partial<
      Pick<RoleListItem, 'roleId' | 'roleName' | 'roleCode' | 'description' | 'enabled'> &
        Api.Common.CommonSearchParams
    >
  }
}
