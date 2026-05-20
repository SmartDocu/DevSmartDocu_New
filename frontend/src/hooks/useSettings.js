import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { message } from 'antd'
import { t } from '@/stores/langStore'
import apiClient from '@/api/client'

// ─── Servers ──────────────────────────────────────────────────────────────────

export function useServers() {
  return useQuery({
    queryKey: ['settings-servers'],
    queryFn: () => apiClient.get('/settings/servers').then((r) => r.data),
  })
}

export function useSaveServer() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body) => apiClient.post('/settings/servers', body).then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['settings-servers'] })
      qc.invalidateQueries({ queryKey: ['datas-dbconnectors'] })
    },
  })
}

export function useDeleteServer() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (connectid) => apiClient.delete(`/settings/servers/${connectid}`).then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['settings-servers'] })
      qc.invalidateQueries({ queryKey: ['datas-dbconnectors'] })
    },
  })
}

// ─── Projects ─────────────────────────────────────────────────────────────────

export function useSettingsProjects() {
  return useQuery({
    queryKey: ['settings-projects'],
    queryFn: () => apiClient.get('/settings/projects').then((r) => r.data),
  })
}

export function useSaveProject() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body) => apiClient.post('/settings/projects', body).then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['settings-projects'] })
    },
  })
}

export function useDeleteProject() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (projectid) => apiClient.delete(`/settings/projects/${projectid}`).then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['settings-projects'] })
    },
  })
}

// ─── Tenants ──────────────────────────────────────────────────────────────────

export function useSettingsTenants() {
  return useQuery({
    queryKey: ['settings-tenants'],
    queryFn: () => apiClient.get('/settings/tenants').then((r) => r.data),
  })
}

export function useSaveTenant() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body) => apiClient.post('/settings/tenants', body).then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['settings-tenants'] })
    },
  })
}

export function useDeleteTenant() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (tenantid) => apiClient.delete(`/settings/tenants/${tenantid}`).then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['settings-tenants'] })
    },
  })
}

// ─── MyInfo ───────────────────────────────────────────────────────────────────

export function useMyInfo() {
  return useQuery({
    queryKey: ['myinfo'],
    queryFn: () => apiClient.get('/settings/myinfo').then((r) => r.data),
  })
}

export function useUpdateUsername() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body) => apiClient.post('/settings/myinfo/username', body).then((r) => r.data),
    onSuccess: () => {
      message.success(t('msg.save.success'))
      qc.invalidateQueries({ queryKey: ['myinfo'] })
    },
    onError: (err) => message.error(err.response?.data?.detail || t('msg.save.error')),
  })
}
