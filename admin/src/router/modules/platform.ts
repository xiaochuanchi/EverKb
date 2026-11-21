import { AppRouteRecord } from '@/types/router'

/**
 * 平台运营工作台路由（PLATFORM 专属）
 *
 * 权限约定（2026-11-20 商业化多租户 M5）：
 * - 平台管理员（R_PLATFORM）走本套运营路由，与企业控制台（everkb.ts 的
 *   R_ENT_ADMIN）互不串门；
 * - 每个子路由显式声明 roles，MenuProcessor 不继承父级角色。
 */
export const platformRoutes: AppRouteRecord = {
  path: '/platform',
  name: 'Platform',
  component: '/index/index',
  meta: {
    title: 'menus.platform.title',
    icon: 'ri:dashboard-3-line',
    roles: ['R_PLATFORM']
  },
  children: [
    {
      path: 'enterprise',
      name: 'PlatformEnterprise',
      component: '/platform/enterprise',
      meta: {
        title: 'menus.platform.enterprise',
        roles: ['R_PLATFORM'],
        keepAlive: true,
        fixedTab: true
      }
    }
  ]
}
