import request from '@/utils/http'

/**
 * EverKB 通知中心 API（对齐后端 /api/v1/admin/notifications）
 * 通知来源：文档处理完成/失败事件。含未读数、标记已读。
 */

/** 通知分页列表（按 id 倒序，返回 total + unread + items） */
export function fetchNotifications(params?: {
  unread_only?: boolean
  page?: number
  size?: number
}) {
  return request.get<Api.EverKB.NotificationPage>({
    url: '/api/v1/admin/notifications',
    params
  })
}

/** 未读通知数（供铃铛红点角标） */
export function fetchUnreadCount() {
  return request.get<{ unread: number }>({
    url: '/api/v1/admin/notifications/unread-count'
  })
}

/** 标记单条已读 */
export function markNotificationRead(id: number) {
  return request.post<Api.EverKB.Notification>({
    url: `/api/v1/admin/notifications/${id}/read`
  })
}

/** 全部标记已读 */
export function markAllNotificationsRead() {
  return request.post<{ ok: boolean }>({
    url: '/api/v1/admin/notifications/read-all'
  })
}
