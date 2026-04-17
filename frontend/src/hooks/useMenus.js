import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import apiClient from '@/api/client'
import { useAuthStore } from '@/stores/authStore'
import { App } from 'antd'

export function useMenus() {
  return useQuery({
    queryKey: ['menus'],
    queryFn: () => apiClient.get('/menus').then((r) => r.data.menus),
    staleTime: 10 * 60 * 1000, // 10분
  })
}

export function useFavorites() {
  const { isAuthenticated } = useAuthStore()
  return useQuery({
    queryKey: ['favorites'],
    queryFn: () => apiClient.get('/menus/favorites').then((r) => r.data.favorites),
    enabled: isAuthenticated(),
    staleTime: 5 * 60 * 1000,
  })
}

export function useToggleFavorite() {
  const qc = useQueryClient()
  const { message } = App.useApp()

  return useMutation({
    mutationFn: (menucd) => apiClient.post(`/menus/favorites/${menucd}`).then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['favorites'] })
    },
    onError: (err) => {
      message.error(err.response?.data?.detail || '즐겨찾기 변경에 실패했습니다.')
    },
  })
}
