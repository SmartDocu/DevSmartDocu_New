import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { App } from 'antd'
import apiClient from '@/api/client'
import { t } from '@/stores/langStore'

export function useAdminTerms() {
  return useQuery({
    queryKey: ['terms-admin'],
    queryFn: () => apiClient.get('/terms/admin').then((r) => r.data.terms),
  })
}

export function useTermTranslations(termkey) {
  return useQuery({
    queryKey: ['term-translations', termkey],
    queryFn: () => apiClient.get(`/terms/${termkey}/translations`).then((r) => r.data.translations),
    enabled: !!termkey,
  })
}

export function useSaveTerm() {
  const qc = useQueryClient()
  const { message } = App.useApp()
  return useMutation({
    mutationFn: ({ isNew, termkey, ...body }) =>
      isNew
        ? apiClient.post('/terms', { termkey, ...body }).then((r) => r.data)
        : apiClient.put(`/terms/${termkey}`, { termkey, ...body }).then((r) => r.data),
    onSuccess: () => {
      message.success(t('msg.saved'))
      qc.invalidateQueries({ queryKey: ['terms-admin'] })
    },
    onError: (err) => message.error(err.response?.data?.detail || t('msg.save.error')),
  })
}

export function useDeleteTerm() {
  const qc = useQueryClient()
  const { message } = App.useApp()
  return useMutation({
    mutationFn: (termkey) => apiClient.delete(`/terms/${termkey}`).then((r) => r.data),
    onSuccess: () => {
      message.success(t('msg.deleted'))
      qc.invalidateQueries({ queryKey: ['terms-admin'] })
    },
    onError: (err) => message.error(err.response?.data?.detail || t('msg.delete.error')),
  })
}

export function useSaveTermTranslation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ termkey, languagecd, translated_text }) =>
      apiClient.post(`/terms/${termkey}/translations`, { languagecd, translated_text }).then((r) => r.data),
    onSuccess: (_data, { termkey }) => {
      qc.invalidateQueries({ queryKey: ['term-translations', termkey] })
    },
  })
}

export function useDeleteTermTranslation() {
  const qc = useQueryClient()
  const { message } = App.useApp()
  return useMutation({
    mutationFn: ({ termkey, languagecd }) =>
      apiClient.delete(`/terms/${termkey}/translations/${languagecd}`).then((r) => r.data),
    onSuccess: (_data, { termkey }) => {
      message.success(t('msg.trans.deleted'))
      qc.invalidateQueries({ queryKey: ['term-translations', termkey] })
    },
    onError: (err) => message.error(err.response?.data?.detail || t('msg.delete.error')),
  })
}
