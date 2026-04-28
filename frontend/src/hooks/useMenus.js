import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { App } from 'antd'
import apiClient from '@/api/client'
import { useAuthStore } from '@/stores/authStore'
import { t } from '@/stores/langStore'

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
      message.error(err.response?.data?.detail || t('msg.favorite.error'))
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

export function useMenuCodes(codegroupcd) {
  return useQuery({
    queryKey: ['codes', codegroupcd],
    queryFn: () => apiClient.get('/codes', { params: { codegroupcd } }).then((r) => r.data.codes),
    enabled: !!codegroupcd,
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
      message.success(t('msg.save.success'))
      qc.invalidateQueries({ queryKey: ['menus-admin'] })
      qc.invalidateQueries({ queryKey: ['menus'] })
    },
    onError: (err) => message.error(err.response?.data?.detail || t('msg.save.error')),
  })
}

export function useDeleteMenu() {
  const qc = useQueryClient()
  const { message } = App.useApp()
  return useMutation({
    mutationFn: (menucd) => apiClient.delete(`/menus/${menucd}`).then((r) => r.data),
    onSuccess: () => {
      message.success(t('msg.delete.success'))
      qc.invalidateQueries({ queryKey: ['menus-admin'] })
      qc.invalidateQueries({ queryKey: ['menus'] })
    },
    onError: (err) => message.error(err.response?.data?.detail || t('msg.delete.error')),
  })
}

export function useSaveTranslation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ menucd, languagecd, translated_text }) =>
      apiClient.post(`/menus/${menucd}/translations`, { languagecd, translated_text }).then((r) => r.data),
    onSuccess: (_data, { menucd }) => {
      qc.invalidateQueries({ queryKey: ['menu-translations', menucd] })
    },
  })
}

export function useDeleteTranslation() {
  const qc = useQueryClient()
  const { message } = App.useApp()
  return useMutation({
    mutationFn: ({ menucd, languagecd }) =>
      apiClient.delete(`/menus/${menucd}/translations/${languagecd}`).then((r) => r.data),
    onSuccess: (_data, { menucd }) => {
      message.success(t('msg.delete.success'))
      qc.invalidateQueries({ queryKey: ['menu-translations', menucd] })
    },
    onError: (err) => message.error(err.response?.data?.detail || t('msg.delete.error')),
  })
}
