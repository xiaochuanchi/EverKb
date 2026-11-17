import { AppRouteRecord } from '@/types/router'
import { everkbRoutes } from './everkb'
import { systemRoutes } from './system'

/**
 * 导出所有模块化路由
 */
export const routeModules: AppRouteRecord[] = [everkbRoutes, systemRoutes]
