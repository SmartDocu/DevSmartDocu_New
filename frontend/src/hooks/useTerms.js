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
    // origTermgroupcd: 수정 대상 행을 특정하는 "원래" termgroupcd (termkey만으로는 유일하지 않음).
    // body.termgroupcd는 저장할 새 값 — 편집 중 그룹을 바꾼 경우 둘이 다를 수 있다.
    mutationFn: ({ isNew, termkey, origTermgroupcd, ...body }) =>
      isNew
        ? apiClient.post('/terms', { termkey, ...body }).then((r) => r.data)
        : apiClient.put(`/terms/${termkey}/${origTermgroupcd}`, { termkey, ...body }).then((r) => r.data),
    onSuccess: () => {
      message.success(t('msg.save.success'))
      qc.invalidateQueries({ queryKey: ['terms-admin'] })
    },
    onError: (err) => { message.error(t(err.response?.data?.detail) || t('msg.save.error')) },
  })
}

export function useDeleteTerm() {
  const qc = useQueryClient()
  const { message } = App.useApp()
  return useMutation({
    mutationFn: ({ termkey, termgroupcd }) => apiClient.delete(`/terms/${termkey}/${termgroupcd}`).then((r) => r.data),
    onSuccess: () => {
      message.success(t('msg.delete.success'))
      qc.invalidateQueries({ queryKey: ['terms-admin'] })
    },
    onError: (err) => { message.error(t(err.response?.data?.detail) || t('msg.delete.error')) },
  })
}

export function useSaveTermTranslation() {
  const qc = useQueryClient()
  const { message } = App.useApp()
  return useMutation({
    mutationFn: ({ termkey, languagecd, translated_text }) =>
      apiClient.post(`/terms/${termkey}/translations`, { languagecd, translated_text }).then((r) => r.data),
    onSuccess: (_data, { termkey }) => {
      qc.invalidateQueries({ queryKey: ['term-translations', termkey] })
    },
    onError: (err) => { message.error(t(err.response?.data?.detail) || t('msg.save.error')) },
  })
}

export function useDeleteTermTranslation() {
  const qc = useQueryClient()
  const { message } = App.useApp()
  return useMutation({
    mutationFn: ({ termkey, languagecd }) =>
      apiClient.delete(`/terms/${termkey}/translations/${languagecd}`).then((r) => r.data),
    onSuccess: (_data, { termkey }) => {
      message.success(t('msg.delete.success'))
      qc.invalidateQueries({ queryKey: ['term-translations', termkey] })
    },
    onError: (err) => { message.error(t(err.response?.data?.detail) || t('msg.delete.error')) },
  })
}
