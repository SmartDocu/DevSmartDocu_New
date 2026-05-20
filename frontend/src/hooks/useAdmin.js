import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { message } from 'antd'
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
  return useMutation({
    mutationFn: (body) => apiClient.post('/admin/sample-prompts', body).then((r) => r.data),
    onSuccess: (data, vars) => {
      if (data.success) {
        message.success(data.message || '저장되었습니다.')
        qc.invalidateQueries({ queryKey: ['admin-sample-prompts'] })
      }
    },
    onError: (err) => message.error(err.response?.data?.detail || t('msg.save.error')),
  })
}

export function useDeleteSamplePrompt() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (promptuid) =>
      apiClient.delete(`/admin/sample-prompts/${promptuid}`).then((r) => r.data),
    onSuccess: () => {
      message.success(t('msg.delete.success'))
      qc.invalidateQueries({ queryKey: ['admin-sample-prompts'] })
    },
    onError: (err) => message.error(err.response?.data?.detail || t('msg.delete.error')),
  })
}

// ─── LLM APIs ────────────────────────────────────────────────────────────────

export function useAdminLlmApis() {
  return useQuery({
    queryKey: ['admin-llmapis'],
    queryFn: () => apiClient.get('/admin/llmapis').then((r) => r.data),
  })
}

export function useSaveLlmApi() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body) => apiClient.post('/admin/llmapis', body).then((r) => r.data),
    onSuccess: () => {
      message.success(t('msg.save.success'))
      qc.invalidateQueries({ queryKey: ['admin-llmapis'] })
    },
    onError: (err) => message.error(err.response?.data?.detail || t('msg.save.error')),
  })
}

export function useDeleteLlmApi() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (llmapiuid) =>
      apiClient.delete(`/admin/llmapis/${llmapiuid}`).then((r) => r.data),
    onSuccess: () => {
      message.success(t('msg.delete.success'))
      qc.invalidateQueries({ queryKey: ['admin-llmapis'] })
    },
    onError: (err) => message.error(err.response?.data?.detail || t('msg.delete.error')),
  })
}

// ─── LLMs ────────────────────────────────────────────────────────────────────

export function useAdminLlms() {
  return useQuery({
    queryKey: ['admin-llms'],
    queryFn: () => apiClient.get('/admin/llms').then((r) => r.data),
  })
}

export function useSaveLlm() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body) => apiClient.post('/admin/llms', body).then((r) => r.data),
    onSuccess: () => {
      message.success(t('msg.save.success'))
      qc.invalidateQueries({ queryKey: ['admin-llms'] })
    },
    onError: (err) => message.error(err.response?.data?.detail || t('msg.save.error')),
  })
}

export function useDeleteLlm() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (llmmodelnm) =>
      apiClient.delete(`/admin/llms/${encodeURIComponent(llmmodelnm)}`).then((r) => r.data),
    onSuccess: () => {
      message.success(t('msg.delete.success'))
      qc.invalidateQueries({ queryKey: ['admin-llms'] })
    },
    onError: (err) => message.error(err.response?.data?.detail || t('msg.delete.error')),
  })
}

// ─── Tenant Requests ─────────────────────────────────────────────────────────

export function useAdminTenantRequests() {
  return useQuery({
    queryKey: ['admin-tenant-requests'],
    queryFn: () => apiClient.get('/admin/tenant-requests').then((r) => r.data),
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
  return useMutation({
    mutationFn: (body) => apiClient.post('/admin/user-role', body).then((r) => r.data),
    onSuccess: () => {
      message.success(t('msg.save.success'))
      qc.invalidateQueries({ queryKey: ['admin-user-roles'] })
    },
    onError: (err) => message.error(err.response?.data?.detail || t('msg.save.error')),
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
  return useMutation({
    mutationFn: (body) => apiClient.post('/admin/prompts', body).then((r) => r.data),
    onSuccess: () => {
      message.success(t('msg.save.success'))
      qc.invalidateQueries({ queryKey: ['admin-prompts'] })
    },
    onError: (err) => message.error(err.response?.data?.detail || t('msg.save.error')),
  })
}

export function useDeletePrompt() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (promptkey) =>
      apiClient.delete(`/admin/prompts/${encodeURIComponent(promptkey)}`).then((r) => r.data),
    onSuccess: () => {
      message.success(t('msg.delete.success'))
      qc.invalidateQueries({ queryKey: ['admin-prompts'] })
    },
    onError: (err) => message.error(err.response?.data?.detail || t('msg.delete.error')),
  })
}

export function useSavePromptTranslation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ promptkey, ...body }) =>
      apiClient
        .post(`/admin/prompts/${encodeURIComponent(promptkey)}/translations`, body)
        .then((r) => r.data),
    onSuccess: (_, vars) => {
      qc.invalidateQueries({ queryKey: ['admin-prompt-translations', vars.promptkey] })
    },
    onError: (err) => message.error(err.response?.data?.detail || t('msg.save.error')),
  })
}

export function useDeletePromptTranslation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ promptkey, languagecd }) =>
      apiClient
        .delete(`/admin/prompts/${encodeURIComponent(promptkey)}/translations/${languagecd}`)
        .then((r) => r.data),
    onSuccess: (_, vars) => {
      qc.invalidateQueries({ queryKey: ['admin-prompt-translations', vars.promptkey] })
    },
    onError: (err) => message.error(err.response?.data?.detail || t('msg.delete.error')),
  })
}
