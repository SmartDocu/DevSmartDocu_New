import { useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import apiClient from '@/api/client'
import { useAuthStore } from '@/stores/authStore'
import { useReqStore } from '@/stores/reqStore'
import { supabase } from '@/lib/supabaseClient'

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

export function useMarkNotificationRead() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (notificationuid) => apiClient.post(`/notifications/${notificationuid}/read`).then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['notifications'] })
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
      qc.invalidateQueries({ queryKey: ['notifications'] })
    },
  })
}

export function useDeleteNotification() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (notificationuid) => apiClient.post(`/notifications/${notificationuid}/delete`).then((r) => r.data),
    onSuccess: () => {
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
