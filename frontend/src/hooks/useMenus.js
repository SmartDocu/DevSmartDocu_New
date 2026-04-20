import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { App } from 'antd'
import apiClient from '@/api/client'
import { useAuthStore } from '@/stores/authStore'

export function useMenus() {
  return useQuery({
    queryKey: ['menus'],
    queryFn: () => apiClient.get('/menus').then((r) => r.data.menus),
    staleTime: 10 * 60 * 1000,
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

// ─── 관리자 메뉴 CRUD ─────────────────────────────────────────────────────────

export function useAdminMenus() {
  return useQuery({
    queryKey: ['menus-admin'],
    queryFn: () => apiClient.get('/menus/admin').then((r) => r.data.menus),
  })
}

export function useLanguages() {
  return useQuery({
    queryKey: ['languages'],
    queryFn: () => apiClient.get('/menus/languages').then((r) => r.data.languages),
  })
}

export function useMenuTranslations(menucd) {
  return useQuery({
    queryKey: ['menu-translations', menucd],
    queryFn: () => apiClient.get(`/menus/${menucd}/translations`).then((r) => r.data.translations),
    enabled: !!menucd,
  })
}

export function useSaveMenu() {
  const qc = useQueryClient()
  const { message } = App.useApp()
  return useMutation({
    mutationFn: ({ isNew, menucd, ...body }) =>
      isNew
        ? apiClient.post('/menus', { menucd, ...body }).then((r) => r.data)
        : apiClient.put(`/menus/${menucd}`, { menucd, ...body }).then((r) => r.data),
    onSuccess: () => {
      message.success('저장되었습니다.')
      qc.invalidateQueries({ queryKey: ['menus-admin'] })
      qc.invalidateQueries({ queryKey: ['menus'] })
    },
    onError: (err) => message.error(err.response?.data?.detail || '저장에 실패했습니다.'),
  })
}

export function useDeleteMenu() {
  const qc = useQueryClient()
  const { message } = App.useApp()
  return useMutation({
    mutationFn: (menucd) => apiClient.delete(`/menus/${menucd}`).then((r) => r.data),
    onSuccess: () => {
      message.success('삭제되었습니다.')
      qc.invalidateQueries({ queryKey: ['menus-admin'] })
      qc.invalidateQueries({ queryKey: ['menus'] })
    },
    onError: (err) => message.error(err.response?.data?.detail || '삭제에 실패했습니다.'),
  })
}

export function useSaveTranslation() {
  const qc = useQueryClient()
  const { message } = App.useApp()
  return useMutation({
    mutationFn: ({ menucd, languagecd, translated_text }) =>
      apiClient.post(`/menus/${menucd}/translations`, { languagecd, translated_text }).then((r) => r.data),
    onSuccess: (_data, { menucd }) => {
      message.success('번역이 저장되었습니다.')
      qc.invalidateQueries({ queryKey: ['menu-translations', menucd] })
    },
    onError: (err) => message.error(err.response?.data?.detail || '저장에 실패했습니다.'),
  })
}

export function useDeleteTranslation() {
  const qc = useQueryClient()
  const { message } = App.useApp()
  return useMutation({
    mutationFn: ({ menucd, languagecd }) =>
      apiClient.delete(`/menus/${menucd}/translations/${languagecd}`).then((r) => r.data),
    onSuccess: (_data, { menucd }) => {
      message.success('번역이 삭제되었습니다.')
      qc.invalidateQueries({ queryKey: ['menu-translations', menucd] })
    },
    onError: (err) => message.error(err.response?.data?.detail || '삭제에 실패했습니다.'),
  })
}
