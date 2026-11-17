import { api } from "@/api";

/**
 * API 模块层：按业务域一个文件、函数式导出、注释即接口文档。
 * （组织方式借鉴 pengYanBPM src/api/*.js；与 BPM 差异：TS 强类型 + 解包后的 data 直接为返回值。）
 */

/** 登录入参 */
export interface LoginPayload {
  username: string;
  password: string;
}

/** 登录返回（token 具体字段名以后端 auth API 契约冻结为准，见排期文档 §4） */
export interface LoginResult {
  token: string;
}

/**
 * 账号密码登录。
 *
 * ⚠️ 契约占位：后端 auth API 尚未就绪（排期文档 §4 依赖项），
 * LoginView 当前仍走本地开发令牌；后端冻结契约（路径 / 字段 / token 形式）后
 * 校对此处路径与类型并接线。后端约定失败响应为信封 401，会触发重新登录对话，
 * 因此此处调用无需 silent。
 */
export function login(payload: LoginPayload): Promise<LoginResult> {
  return api.post<LoginResult>("/api/v1/auth/login", payload);
}
