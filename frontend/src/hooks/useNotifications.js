import { useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import apiClient from '@/api/client'
import { useAuthStore } from '@/stores/authStore'
import { useReqStore } from '@/stores/reqStore'
import { supabase } from '@/lib/supabaseClient'
import { t } from '@/stores/langStore'

// 알림 title/message 번역 렌더링 — titlekey/messagekey(ui_terms의 msg.* term_key)가 있으면
// 로그인 언어로 번역하고 params의 값으로 {placeholder}를 치환. 키가 없는 레거시 알림은
// 백엔드가 생성 시점에 넣어둔 한글 title/message를 그대로 사용(t()의 fallback으로 처리됨).
export function translateNotification(n) {
  const title = t(n.titlekey, n.title)
  let message = t(n.messagekey, n.message)
  if (n.params) {
    for (const [key, value] of Object.entries(n.params)) {
      message = message.replaceAll(`{${key}}`, value)
    }
  }
  return { title, message }
}

export function useNotifications() {
  const userId = useAuthStore((s) => s.user?.id)
  const qc = useQueryClient()

  const query = useQuery({
    queryKey: ['notifications'],
    queryFn: () => apiClient.get('/notifications', { params: { unread_only: true } }).then((r) => r.data),
    enabled: !!userId,
  })

  useEffect(() => {
    if (!userId) return
    const invalidate = () => qc.invalidateQueries({ queryKey: ['notifications'] })

    const ownChannel = supabase
      .channel(`notifications_${userId}`)
      .on(
        'postgres_changes',
        { event: '*', schema: 'sdoc', table: 'notifications', filter: `target_useruid=eq.${userId}` },
        invalidate,
      )
      .subscribe()

    // 다중 대상 알림 — notification_users에 내 앞으로 새 row가 생기거나 갱신되면 목록 갱신
    const sharedChannel = supabase
      .channel(`notification_users_${userId}`)
      .on(
        'postgres_changes',
        { event: '*', schema: 'sdoc', table: 'notification_users', filter: `target_useruid=eq.${userId}` },
        invalidate,
      )
      .subscribe()

    return () => {
      supabase.removeChannel(ownChannel)
      supabase.removeChannel(sharedChannel)
    }
  }, [userId]) // eslint-disable-line react-hooks/exhaustive-deps

  return query
}

// 알림 관련 쿼리(헤더 벨 + 목록 화면의 모든 필터 조합)를 한 번에 직접 패치한다.
// invalidateQueries만으로는 새로고침 전까지 화면이 갱신되지 않는 문제가 있어,
// mutate 성공 시 캐시를 즉시 갱신하고 invalidate는 최종 동기화용으로 함께 호출한다.
function patchNotificationsCache(qc, updater) {
  qc.setQueriesData({ queryKey: ['notifications'] }, (old) => {
    if (!old || !Array.isArray(old.notifications)) return old
    const notifications = updater(old.notifications)
    return { ...old, notifications, unread_count: notifications.filter((n) => !n.is_read).length }
  })
}

export function useMarkNotificationRead() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (notificationuid) => apiClient.post(`/notifications/${notificationuid}/read`).then((r) => r.data),
    // invalidate를 하지 않는다 — "안읽음" 필터에서 방금 읽은 row가 즉시 사라지면
    // 펼쳐놓은 이동/삭제 버튼을 누르기 전에 화면에서 사라져버리는 문제가 있음.
    // 캐시만 직접 패치해 배경색만 바꾸고, 실제 제외는 다음 필터 변경/새로고침 때 반영.
    onSuccess: (_data, notificationuid) => {
      patchNotificationsCache(qc, (list) =>
        list.map((n) => (n.notificationuid === notificationuid ? { ...n, is_read: true } : n)),
      )
    },
  })
}

export function useNotificationsList({ category, notificationStatus, readStatus, search, page = 1, pageSize = 20 } = {}) {
  const userId = useAuthStore((s) => s.user?.id)
  const offset = (page - 1) * pageSize

  return useQuery({
    queryKey: ['notifications', 'list', category || null, notificationStatus || null, readStatus || null, search || null, page, pageSize],
    queryFn: () => apiClient.get('/notifications', {
      params: {
        category: category || undefined,
        notification_status: notificationStatus || undefined,
        read_status: readStatus || undefined,
        search: search || undefined,
        offset,
        limit: pageSize,
      },
    }).then((r) => r.data),
    enabled: !!userId,
  })
}

export function useMarkAllNotificationsRead() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => apiClient.post('/notifications/read-all').then((r) => r.data),
    onSuccess: () => {
      patchNotificationsCache(qc, (list) => list.map((n) => ({ ...n, is_read: true })))
      qc.invalidateQueries({ queryKey: ['notifications'] })
    },
  })
}

export function useDeleteNotification() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (notificationuid) => apiClient.post(`/notifications/${notificationuid}/delete`).then((r) => r.data),
    onSuccess: (_data, notificationuid) => {
      patchNotificationsCache(qc, (list) => list.filter((n) => n.notificationuid !== notificationuid))
      qc.invalidateQueries({ queryKey: ['notifications'] })
    },
  })
}

// 알림 클릭 시 이동 로직 — 헤더 팝업/알림 목록 화면에서 공용으로 사용
// target_url 형식: '/app/:appcd' 접두사 없는 상대 경로 + (선택) 쿼리스트링
// 예) 'req/chapters-read?genchapteruid=xxx'
// req/doc-read, req/chapters-read는 URL 쿼리가 아니라 useReqStore(activeGendocuid/activeGenchapteruid)로
// 현재 문서·챕터를 선택하는 구조라, target_url로 이동하기 전에 스토어도 같이 채워준다.
export function navigateToNotificationTarget(n, openInTab) {
  if (!n.target_url) return
  if ((n.target_object === 'gendoc' || n.target_object === 'genchapter') && n.target_uid) {
    useReqStore.getState().setActiveGendocuid(n.target_uid)
  }
  const [routePath, queryString] = n.target_url.replace(/^\//, '').split('?')
  if (queryString) {
    const genchapteruid = new URLSearchParams(queryString).get('genchapteruid')
    if (genchapteruid) useReqStore.getState().setActiveGenchapteruid(genchapteruid)
  }
  openInTab(routePath, queryString ? `?${queryString}` : '')
}
