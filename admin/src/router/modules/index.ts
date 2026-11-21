import { AppRouteRecord } from '@/types/router'
import { everkbRoutes } from './everkb'
import { platformRoutes } from './platform'
import { systemRoutes } from './system'

/**
 * 导出所有模块化路由
 */
export const routeModules: AppRouteRecord[] = [everkbRoutes, platformRoutes, systemRoutes]
