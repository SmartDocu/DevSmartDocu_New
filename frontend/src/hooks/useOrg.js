import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { message } from 'antd'
import { t } from '@/stores/langStore'
import apiClient from '@/api/client'

// ─── Tenant LLMs ──────────────────────────────────────────────────────────────

export function useOrgTenantLlms() {
  return useQuery({
    queryKey: ['org-tenant-llms'],
    queryFn: () => apiClient.get('/org/tenant-llms').then((r) => r.data),
  })
}

export function useSaveTenantLlm() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body) => apiClient.post('/org/tenant-llms', body).then((r) => r.data),
    onSuccess: () => {
      message.success(t('msg.save.success'))
      qc.invalidateQueries({ queryKey: ['org-tenant-llms'] })
    },
    onError: (err) => message.error(err.response?.data?.detail || t('msg.save.error')),
  })
}

export function useDeleteTenantLlm() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body) =>
      apiClient.delete('/org/tenant-llms', { data: body }).then((r) => r.data),
    onSuccess: () => {
      message.success(t('msg.delete.success'))
      qc.invalidateQueries({ queryKey: ['org-tenant-llms'] })
    },
    onError: (err) => message.error(err.response?.data?.detail || t('msg.delete.error')),
  })
}

// ─── Projects ─────────────────────────────────────────────────────────────────

export function useOrgProjects(tenantid) {
  return useQuery({
    queryKey: ['org-projects', tenantid],
    queryFn: () =>
      apiClient
        .get('/org/projects', { params: tenantid ? { tenantid } : {} })
        .then((r) => r.data),
  })
}

export function useSaveOrgProject() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body) => apiClient.post('/org/projects', body).then((r) => r.data),
    onSuccess: (_, vars) => {
      message.success(t('msg.save.success'))
      qc.invalidateQueries({ queryKey: ['org-projects', vars.tenantid] })
      qc.invalidateQueries({ queryKey: ['org-projects'] })
    },
    onError: (err) => message.error(err.response?.data?.detail || t('msg.save.error')),
  })
}

export function useDeleteOrgProject() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ projectid }) =>
      apiClient.delete(`/org/projects/${projectid}`).then((r) => r.data),
    onSuccess: (_, vars) => {
      message.success(t('msg.delete.success'))
      qc.invalidateQueries({ queryKey: ['org-projects'] })
    },
    onError: (err) => message.error(err.response?.data?.detail || t('msg.delete.error')),
  })
}

// ─── Project Users ────────────────────────────────────────────────────────────

export function useOrgProjectUsers(projectid) {
  return useQuery({
    queryKey: ['org-project-users', projectid],
    queryFn: () =>
      apiClient
        .get('/org/project-users', { params: projectid ? { projects: projectid } : {} })
        .then((r) => r.data),
  })
}

export function useSaveProjectUser() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body) => apiClient.post('/org/project-users', body).then((r) => r.data),
    onSuccess: (_, vars) => {
      qc.invalidateQueries({ queryKey: ['org-project-users', vars.projectid] })
    },
  })
}

export function useDeleteProjectUser() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body) =>
      apiClient.delete('/org/project-users', { data: body }).then((r) => r.data),
    onSuccess: (_, vars) => {
      qc.invalidateQueries({ queryKey: ['org-project-users', vars.projectid] })
    },
  })
}

// ─── Tenant Users ─────────────────────────────────────────────────────────────

export function useOrgTenantUsers(tenantid) {
  return useQuery({
    queryKey: ['org-tenant-users', tenantid],
    queryFn: () =>
      apiClient
        .get('/org/tenant-users', { params: tenantid ? { tenantid } : {} })
        .then((r) => r.data),
  })
}

export function useSaveTenantUser() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body) => apiClient.post('/org/tenant-users', body).then((r) => r.data),
    onSuccess: (_, vars) => {
      message.success(t('msg.save.success'))
      qc.invalidateQueries({ queryKey: ['org-tenant-users', vars.tenantid] })
      qc.invalidateQueries({ queryKey: ['org-tenant-users'] })
    },
    onError: (err) => message.error(err.response?.data?.detail || t('msg.save.error')),
  })
}

export function useDeleteTenantUser() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body) =>
      apiClient.delete('/org/tenant-users', { data: body }).then((r) => r.data),
    onSuccess: (_, vars) => {
      message.success(t('msg.delete.success'))
      qc.invalidateQueries({ queryKey: ['org-tenant-users', vars.tenantid] })
      qc.invalidateQueries({ queryKey: ['org-tenant-users'] })
    },
    onError: (err) => message.error(err.response?.data?.detail || t('msg.delete.error')),
  })
}
