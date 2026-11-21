import { AppRouteRecord } from '@/types/router'

/**
 * EverKB 企业控制台路由（ENT_ADMIN 专属）
 *
 * 权限约定（2026-11-20 商业化多租户 M5）：
 * - 每个子路由显式声明 roles——MenuProcessor 不继承父级角色，漏写即暴露；
 * - M5 起本套业务路由归企业管理员（R_ENT_ADMIN）；平台管理员（R_PLATFORM）
 *   走独立的 platform 运营工作台路由（见 platform.ts），互不串门；
 * - 旧 trial 体验中心单页已废弃删除。
 */
export const everkbRoutes: AppRouteRecord = {
  path: '/everkb',
  name: 'EverKB',
  component: '/index/index',
  meta: {
    title: 'menus.everkb.title',
    icon: 'ri:database-2-line',
    roles: ['R_ENT_ADMIN']
  },
  children: [
    {
      path: 'dashboard',
      name: 'EverKBDashboard',
      component: '/everkb/dashboard',
      meta: {
        title: 'menus.everkb.dashboard',
        roles: ['R_ENT_ADMIN'],
        keepAlive: true,
        fixedTab: true
      }
    },
    {
      path: 'knowledge',
      name: 'EverKBKnowledge',
      component: '/everkb/knowledge',
      meta: { title: 'menus.everkb.knowledge', roles: ['R_ENT_ADMIN'], keepAlive: true }
    },
    {
      path: 'document',
      name: 'EverKBDocument',
      component: '/everkb/document',
      meta: { title: 'menus.everkb.document', roles: ['R_ENT_ADMIN'], keepAlive: true }
    },
    {
      // md 编辑器：/everkb/editor?docId=xxx
      path: 'editor',
      name: 'EverKBDocumentEditor',
      component: '/everkb/document/editor',
      meta: {
        title: 'menus.everkb.documentEditor',
        roles: ['R_ENT_ADMIN'],
        isHide: true,
        keepAlive: false
      }
    },
    {
      // chunk 浏览：/everkb/chunk?docId=xxx
      path: 'chunk',
      name: 'EverKBChunk',
      component: '/everkb/chunk',
      meta: { title: 'menus.everkb.chunk', roles: ['R_ENT_ADMIN'], keepAlive: true }
    },
    {
      path: 'app',
      name: 'EverKBApp',
      component: '/everkb/app',
      meta: { title: 'menus.everkb.app', roles: ['R_ENT_ADMIN'], keepAlive: true }
    },
    {
      path: 'qa-record',
      name: 'EverKBQaRecord',
      component: '/everkb/qa-record',
      meta: { title: 'menus.everkb.qaRecord', roles: ['R_ENT_ADMIN'], keepAlive: true }
    },
    {
      path: 'trace',
      name: 'EverKBTrace',
      component: '/everkb/trace',
      meta: { title: 'menus.everkb.trace', roles: ['R_ENT_ADMIN'], keepAlive: true }
    },
    {
      // Trace 详情：/everkb/trace-detail?traceId=xxx（Span 树 + 时间轴）
      path: 'trace-detail',
      name: 'EverKBTraceDetail',
      component: '/everkb/trace/detail',
      meta: {
        title: 'menus.everkb.traceDetail',
        roles: ['R_ENT_ADMIN'],
        isHide: true,
        keepAlive: false
      }
    },
    {
      path: 'reconcile',
      name: 'EverKBReconcile',
      component: '/everkb/reconcile',
      meta: { title: 'menus.everkb.reconcile', roles: ['R_ENT_ADMIN'], keepAlive: true }
    },
    {
      // 检索评测：三路消融指标对比
      path: 'eval',
      name: 'EverKBEval',
      component: '/everkb/eval',
      meta: { title: 'menus.everkb.eval', roles: ['R_ENT_ADMIN'], keepAlive: true }
    },
    {
      // 企业钱包：余额 + 消费流水（M5 钱包页）
      path: 'wallet',
      name: 'EverKBWallet',
      component: '/everkb/wallet',
      meta: { title: 'menus.everkb.wallet', roles: ['R_ENT_ADMIN'], keepAlive: true }
    }
  ]
}
