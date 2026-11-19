import { AppRouteRecord } from '@/types/router'

/**
 * EverKB 业务路由（一期 9 页，见设计文档 §7）
 * 页面批次 1/2 逐步实现，当前为占位骨架
 */
export const everkbRoutes: AppRouteRecord = {
  path: '/everkb',
  name: 'EverKB',
  component: '/index/index',
  meta: {
    title: 'menus.everkb.title',
    icon: 'ri:database-2-line',
    roles: ['R_SUPER', 'R_ADMIN']
  },
  children: [
    {
      path: 'dashboard',
      name: 'EverKBDashboard',
      component: '/everkb/dashboard',
      meta: { title: 'menus.everkb.dashboard', keepAlive: true, fixedTab: true }
    },
    {
      path: 'knowledge',
      name: 'EverKBKnowledge',
      component: '/everkb/knowledge',
      meta: { title: 'menus.everkb.knowledge', keepAlive: true }
    },
    {
      path: 'document',
      name: 'EverKBDocument',
      component: '/everkb/document',
      meta: { title: 'menus.everkb.document', keepAlive: true }
    },
    {
      // md 编辑器：/everkb/editor?docId=xxx，编辑 content.md（批次 2 实现）
      path: 'editor',
      name: 'EverKBDocumentEditor',
      component: '/everkb/document/editor',
      meta: { title: 'menus.everkb.documentEditor', isHide: true, keepAlive: false }
    },
    {
      path: 'chunk',
      name: 'EverKBChunk',
      component: '/everkb/chunk',
      meta: { title: 'menus.everkb.chunk', keepAlive: true }
    },
    {
      path: 'app',
      name: 'EverKBApp',
      component: '/everkb/app',
      meta: { title: 'menus.everkb.app', keepAlive: true }
    },
    {
      path: 'qa-record',
      name: 'EverKBQaRecord',
      component: '/everkb/qa-record',
      meta: { title: 'menus.everkb.qaRecord', keepAlive: true }
    },
    {
      path: 'trace',
      name: 'EverKBTrace',
      component: '/everkb/trace',
      meta: { title: 'menus.everkb.trace', keepAlive: true }
    },
    {
      // Trace 详情：/everkb/trace-detail?traceId=xxx（Span 树 + 时间轴）
      path: 'trace-detail',
      name: 'EverKBTraceDetail',
      component: '/everkb/trace/detail',
      meta: { title: 'menus.everkb.traceDetail', isHide: true, keepAlive: false }
    },
    {
      path: 'reconcile',
      name: 'EverKBReconcile',
      component: '/everkb/reconcile',
      meta: { title: 'menus.everkb.reconcile', keepAlive: true }
    },
    {
      // 检索评测：/everkb/eval（二期 Task 28 可视化，三路消融指标对比）
      path: 'eval',
      name: 'EverKBEval',
      component: '/everkb/eval',
      meta: { title: 'menus.everkb.eval', keepAlive: true }
    }
  ]
}
