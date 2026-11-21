/**
 * EverKB 业务枚举的运行时值（对齐 backend/app/models.py）
 *
 * 注意：Api.EverKB 命名空间在 .d.ts 中只有类型（declare enum 无运行时值），
 * 模板/逻辑里需要比较状态值时一律 import 本文件的常量。
 */

/** 知识库状态（models.KBStatus） */
export const KB_STATUS = {
  Disabled: 0,
  Enabled: 1
} as const

/** 文档状态机（models.DocumentStatus）：1→2→3→4→5→6，任一环节失败→7 */
export const DOC_STATUS = {
  Uploaded: 1,
  Parsing: 2,
  Extracted: 3,
  Chunked: 4,
  Vectorizing: 5,
  Completed: 6,
  Failed: 7
} as const

/** 文档来源（models.SourceType） */
export const DOC_SOURCE_TYPE = {
  Upload: 1,
  Webpage: 2
} as const

/** 用户反馈（models.Feedback）：0 未反馈 / 1 满意 / -1 不满意 */
export const FEEDBACK = {
  None: 0,
  Good: 1,
  Bad: -1
} as const

/** 企业生命周期状态（models.EnterpriseStatus）：1 试用 / 2 正式 / 3 冻结 / 4 已清理 */
export const ENTERPRISE_STATUS = {
  Trial: 1,
  Active: 2,
  Frozen: 3,
  Purged: 4
} as const
