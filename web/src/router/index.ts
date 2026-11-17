import { createRouter, createWebHistory } from "vue-router";

import { useAuthStore } from "@/stores/auth";

/**
 * 路由 + 守卫壳（F0）。
 * 页面用动态 import，避免与 api 单例形成静态环：api/index → router → (lazy) views → api/index。
 * meta.public：白名单路由（登录页 / 404），不校验登录态。
 */
const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: "/login",
      name: "login",
      component: () => import("@/views/LoginView.vue"),
      meta: { public: true },
    },
    {
      path: "/",
      name: "chat",
      component: () => import("@/views/ChatView.vue"),
    },
    {
      path: "/:pathMatch(.*)*",
      name: "not-found",
      component: () => import("@/views/NotFoundView.vue"),
      meta: { public: true },
    },
  ],
});

router.beforeEach((to) => {
  const auth = useAuthStore();
  if (to.meta.public || auth.isAuthenticated) {
    return true;
  }
  return { name: "login", query: { redirect: to.fullPath } };
});

export default router;
