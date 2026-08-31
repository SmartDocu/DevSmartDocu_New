import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { App } from 'antd'
import { t } from '@/stores/langStore'
import apiClient from '@/api/client'

// ─── Help Search ──────────────────────────────────────────────────────────────

export function useHelpSearch(url, languagecd) {
  return useQuery({
    queryKey: ['help-search', url, languagecd],
    queryFn: () =>
      apiClient.get('/admin/helps/search', { params: { url, languagecd } }).then(r => r.data),
    enabled: !!url && !!languagecd,
    staleTime: 10 * 60 * 1000,
  })
}

// ─── Sample Prompts ───────────────────────────────────────────────────────────

export function useAdminSamplePrompts(objectType, displaytype) {
  return useQuery({
    queryKey: ['admin-sample-prompts', objectType, displaytype],
    queryFn: () =>
      apiClient
        .get('/admin/sample-prompts', {
          params: { object_type: objectType, ...(displaytype ? { displaytype } : {}) },
        })
        .then((r) => r.data),
    enabled: !!objectType,
  })
}

export function useSaveSamplePrompt() {
  const qc = useQueryClient()
  const { message } = App.useApp()
  return useMutation({
    mutationFn: (body) => apiClient.post('/admin/sample-prompts', body).then((r) => r.data),
    onSuccess: (data, vars) => {
      if (data.success) {
        message.success(data.message || t('msg.save.success'))
        qc.invalidateQueries({ queryKey: ['admin-sample-prompts'] })
      }
    },
    onError: (err) => { message.error(err.response?.data?.detail || t('msg.save.error')) },
  })
}

export function useDeleteSamplePrompt() {
  const qc = useQueryClient()
  const { message } = App.useApp()
  return useMutation({
    mutationFn: (promptuid) =>
      apiClient.delete(`/admin/sample-prompts/${promptuid}`).then((r) => r.data),
    onSuccess: () => {
      message.success(t('msg.delete.success'))
      qc.invalidateQueries({ queryKey: ['admin-sample-prompts'] })
    },
    onError: (err) => { message.error(err.response?.data?.detail || t('msg.delete.error')) },
  })
}

// ─── Billing Recovery (PastDue/Suspended 계정 조회 + 수동 재청구) ──────────────

export function useBillingRecoveryAccounts() {
  return useQuery({
    queryKey: ['admin-billing-recovery'],
    queryFn: () => apiClient.get('/admin/billing-recovery').then((r) => r.data),
  })
}

export function useRetryBillingRecovery() {
  const qc = useQueryClient()
  const { message } = App.useApp()
  return useMutation({
    mutationFn: (accountuid) => apiClient.post(`/admin/billing-recovery/${accountuid}/retry`).then((r) => r.data),
    onSuccess: () => {
      message.success(t('msg.billing.retry.success'))
      qc.invalidateQueries({ queryKey: ['admin-billing-recovery'] })
    },
    onError: (err) => { message.error(err.response?.data?.detail || t('msg.billing.retry.error')) },
  })
}

// ─── User Role ────────────────────────────────────────────────────────────────

export function useAdminUserRoles() {
  return useQuery({
    queryKey: ['admin-user-roles'],
    queryFn: () => apiClient.get('/admin/user-role').then((r) => r.data),
  })
}

export function useSaveUserRole() {
  const qc = useQueryClient()
  const { message } = App.useApp()
  return useMutation({
    mutationFn: (body) => apiClient.post('/admin/user-role', body).then((r) => r.data),
    onSuccess: () => {
      message.success(t('msg.save.success'))
      qc.invalidateQueries({ queryKey: ['admin-user-roles'] })
    },
    onError: (err) => { message.error(err.response?.data?.detail || t('msg.save.error')) },
  })
}

// ─── Prompts (sdoc.prompts) ───────────────────────────────────────────────────

export function usePromptSampleDatas() {
  return useQuery({
    queryKey: ['admin-prompt-sample-datas'],
    queryFn: () => apiClient.get('/admin/prompts/sample-datas').then((r) => r.data.datas),
  })
}

export function useAdminPrompts() {
  return useQuery({
    queryKey: ['admin-prompts'],
    queryFn: () => apiClient.get('/admin/prompts').then((r) => r.data.prompts),
  })
}

export function usePromptTranslations(promptkey) {
  return useQuery({
    queryKey: ['admin-prompt-translations', promptkey],
    queryFn: () =>
      apiClient.get(`/admin/prompts/${encodeURIComponent(promptkey)}/translations`).then((r) => r.data.translations),
    enabled: !!promptkey,
  })
}

export function useSavePrompt() {
  const qc = useQueryClient()
  const { message } = App.useApp()
  return useMutation({
    mutationFn: (body) => apiClient.post('/admin/prompts', body).then((r) => r.data),
    onSuccess: () => {
      message.success(t('msg.save.success'))
      qc.invalidateQueries({ queryKey: ['admin-prompts'] })
    },
    onError: (err) => { message.error(err.response?.data?.detail || t('msg.save.error')) },
  })
}

export function useDeletePrompt() {
  const qc = useQueryClient()
  const { message } = App.useApp()
  return useMutation({
    mutationFn: (promptkey) =>
      apiClient.delete(`/admin/prompts/${encodeURIComponent(promptkey)}`).then((r) => r.data),
    onSuccess: () => {
      message.success(t('msg.delete.success'))
      qc.invalidateQueries({ queryKey: ['admin-prompts'] })
    },
    onError: (err) => { message.error(err.response?.data?.detail || t('msg.delete.error')) },
  })
}

export function useSavePromptTranslation() {
  const qc = useQueryClient()
  const { message } = App.useApp()
  return useMutation({
    mutationFn: ({ promptkey, ...body }) =>
      apiClient
        .post(`/admin/prompts/${encodeURIComponent(promptkey)}/translations`, body)
        .then((r) => r.data),
    onSuccess: (_, vars) => {
      qc.invalidateQueries({ queryKey: ['admin-prompt-translations', vars.promptkey] })
    },
    onError: (err) => { message.error(err.response?.data?.detail || t('msg.save.error')) },
  })
}

export function useDeletePromptTranslation() {
  const qc = useQueryClient()
  const { message } = App.useApp()
  return useMutation({
    mutationFn: ({ promptkey, languagecd }) =>
      apiClient
        .delete(`/admin/prompts/${encodeURIComponent(promptkey)}/translations/${languagecd}`)
        .then((r) => r.data),
    onSuccess: (_, vars) => {
      qc.invalidateQueries({ queryKey: ['admin-prompt-translations', vars.promptkey] })
    },
    onError: (err) => { message.error(err.response?.data?.detail || t('msg.delete.error')) },
  })
}
