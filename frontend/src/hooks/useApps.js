import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { App } from 'antd'
import apiClient from '@/api/client'
import { t } from '@/stores/langStore'

export function useApps({ enabled = true, tenantid, languagecd } = {}) {
  return useQuery({
    queryKey: ['apps', tenantid, languagecd],
    queryFn: () =>
      apiClient.get('/apps', { params: { ...(tenantid ? { tenantid } : {}), ...(languagecd ? { languagecd } : {}) } }).then((r) => r.data),
    staleTime: 10 * 60 * 1000,
    enabled,
  })
}

export function useAppTranslations(appcd) {
  return useQuery({
    queryKey: ['app-translations', appcd],
    queryFn: () => apiClient.get(`/apps/${appcd}/translations`).then((r) => r.data.translations),
    enabled: !!appcd,
  })
}

export function useSaveAppTranslation() {
  const qc = useQueryClient()
  const { message } = App.useApp()
  return useMutation({
    mutationFn: ({ appcd, languagecd, translated_text }) =>
      apiClient.post(`/apps/${appcd}/translations`, { languagecd, translated_text }).then((r) => r.data),
    onSuccess: (_data, { appcd }) => {
      qc.invalidateQueries({ queryKey: ['app-translations', appcd] })
      qc.invalidateQueries({ queryKey: ['apps'] })
    },
    onError: (err) => { message.error(err.response?.data?.detail || t('msg.save.error')) },
  })
}

export function useDeleteAppTranslation() {
  const qc = useQueryClient()
  const { message } = App.useApp()
  return useMutation({
    mutationFn: ({ appcd, languagecd }) =>
      apiClient.delete(`/apps/${appcd}/translations/${languagecd}`).then((r) => r.data),
    onSuccess: (_data, { appcd }) => {
      message.success(t('msg.delete.success'))
      qc.invalidateQueries({ queryKey: ['app-translations', appcd] })
      qc.invalidateQueries({ queryKey: ['apps'] })
    },
    onError: (err) => { message.error(err.response?.data?.detail || t('msg.delete.error')) },
  })
}
