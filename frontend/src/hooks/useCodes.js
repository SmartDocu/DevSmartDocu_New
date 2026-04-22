import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { App } from 'antd'
import apiClient from '@/api/client'
import { t } from '@/stores/langStore'

export function useAdminCodes() {
  return useQuery({
    queryKey: ['codes-admin'],
    queryFn: () => apiClient.get('/codes/admin').then((r) => r.data.codes),
  })
}

export function useCodeTranslations(codegroupcd, codevalue) {
  return useQuery({
    queryKey: ['code-translations', codegroupcd, codevalue],
    queryFn: () => apiClient.get(`/codes/${codegroupcd}/${codevalue}/translations`).then((r) => r.data.translations),
    enabled: !!codegroupcd && !!codevalue,
  })
}

export function useSaveCode() {
  const qc = useQueryClient()
  const { message } = App.useApp()
  return useMutation({
    mutationFn: ({ isNew, codegroupcd, codevalue, ...body }) =>
      isNew
        ? apiClient.post('/codes', { codegroupcd, codevalue, ...body }).then((r) => r.data)
        : apiClient.put(`/codes/${codegroupcd}/${codevalue}`, { codegroupcd, codevalue, ...body }).then((r) => r.data),
    onSuccess: () => {
      message.success(t('msg.saved'))
      qc.invalidateQueries({ queryKey: ['codes-admin'] })
    },
    onError: (err) => message.error(err.response?.data?.detail || t('msg.save.error')),
  })
}

export function useDeleteCode() {
  const qc = useQueryClient()
  const { message } = App.useApp()
  return useMutation({
    mutationFn: ({ codegroupcd, codevalue }) => apiClient.delete(`/codes/${codegroupcd}/${codevalue}`).then((r) => r.data),
    onSuccess: () => {
      message.success(t('msg.deleted'))
      qc.invalidateQueries({ queryKey: ['codes-admin'] })
    },
    onError: (err) => message.error(err.response?.data?.detail || t('msg.delete.error')),
  })
}

export function useSaveCodeTranslation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ codegroupcd, codevalue, languagecd, translated_text, translated_desc }) =>
      apiClient.post(`/codes/${codegroupcd}/${codevalue}/translations`, { languagecd, translated_text, translated_desc }).then((r) => r.data),
    onSuccess: (_data, { codegroupcd, codevalue }) => {
      qc.invalidateQueries({ queryKey: ['code-translations', codegroupcd, codevalue] })
    },
  })
}

export function useDeleteCodeTranslation() {
  const qc = useQueryClient()
  const { message } = App.useApp()
  return useMutation({
    mutationFn: ({ codegroupcd, codevalue, languagecd }) =>
      apiClient.delete(`/codes/${codegroupcd}/${codevalue}/translations/${languagecd}`).then((r) => r.data),
    onSuccess: (_data, { codegroupcd, codevalue }) => {
      message.success(t('msg.trans.deleted'))
      qc.invalidateQueries({ queryKey: ['code-translations', codegroupcd, codevalue] })
    },
    onError: (err) => message.error(err.response?.data?.detail || t('msg.delete.error')),
  })
}
