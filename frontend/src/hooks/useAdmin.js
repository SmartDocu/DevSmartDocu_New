import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { message } from 'antd'
import apiClient from '@/api/client'

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
    onError: (err) => message.error(err.response?.data?.detail || '저장에 실패했습니다.'),
  })
}

export function useDeleteSamplePrompt() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (promptuid) =>
      apiClient.delete(`/admin/sample-prompts/${promptuid}`).then((r) => r.data),
    onSuccess: () => {
      message.success('삭제되었습니다.')
      qc.invalidateQueries({ queryKey: ['admin-sample-prompts'] })
    },
    onError: (err) => message.error(err.response?.data?.detail || '삭제에 실패했습니다.'),
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
      message.success('저장되었습니다.')
      qc.invalidateQueries({ queryKey: ['admin-llmapis'] })
    },
    onError: (err) => message.error(err.response?.data?.detail || '저장에 실패했습니다.'),
  })
}

export function useDeleteLlmApi() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (llmapiuid) =>
      apiClient.delete(`/admin/llmapis/${llmapiuid}`).then((r) => r.data),
    onSuccess: () => {
      message.success('삭제되었습니다.')
      qc.invalidateQueries({ queryKey: ['admin-llmapis'] })
    },
    onError: (err) => message.error(err.response?.data?.detail || '삭제에 실패했습니다.'),
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
      message.success('저장되었습니다.')
      qc.invalidateQueries({ queryKey: ['admin-llms'] })
    },
    onError: (err) => message.error(err.response?.data?.detail || '저장에 실패했습니다.'),
  })
}

export function useDeleteLlm() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (llmmodelnm) =>
      apiClient.delete(`/admin/llms/${encodeURIComponent(llmmodelnm)}`).then((r) => r.data),
    onSuccess: () => {
      message.success('삭제되었습니다.')
      qc.invalidateQueries({ queryKey: ['admin-llms'] })
    },
    onError: (err) => message.error(err.response?.data?.detail || '삭제에 실패했습니다.'),
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
      message.success('권한이 변경되었습니다.')
      qc.invalidateQueries({ queryKey: ['admin-user-roles'] })
    },
    onError: (err) => message.error(err.response?.data?.detail || '변경에 실패했습니다.'),
  })
}
