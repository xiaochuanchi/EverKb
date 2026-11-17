import { defineStore } from "pinia";

const TOKEN_KEY = "everkb_web_token";

function readToken(): string | null {
  // SSR / 无痕模式兜底：localStorage 不可用时退化为仅内存态
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

/**
 * 登录态 store（F0 只管 token 的存取与清理）。
 * 登录 API 尚未就绪（后端缺口，见排期文档 §4）：LoginView 目前写入开发占位令牌，
 * 后端 auth API 就绪后由调用方改为 setToken(接口返回值)。
 */
export const useAuthStore = defineStore("auth", {
  state: () => ({
    token: readToken(),
  }),
  getters: {
    /** 守卫判据：一期仅判断令牌存在，Token 校验由后端 401 兜底 */
    isAuthenticated: (state): boolean => state.token !== null,
  },
  actions: {
    setToken(token: string): void {
      this.token = token;
      try {
        localStorage.setItem(TOKEN_KEY, token);
      } catch {
        // 内存态已更新，静默降级
      }
    },
    clear(): void {
      this.token = null;
      try {
        localStorage.removeItem(TOKEN_KEY);
      } catch {
        // 同上
      }
    },
  },
});
