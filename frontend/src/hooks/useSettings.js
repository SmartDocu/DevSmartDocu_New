import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { message } from 'antd'
import { t } from '@/stores/langStore'
import apiClient from '@/api/client'
import { useAuthStore } from '@/stores/authStore'

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
      qc.invalidateQueries({ queryKey: ['dbconnectors'] })
    },
  })
}

export function useDeleteServer() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (connuid) => apiClient.delete(`/settings/servers/${connuid}`).then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['settings-servers'] })
      qc.invalidateQueries({ queryKey: ['dbconnectors'] })
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

export function useUpdateTimezone() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body) => apiClient.post('/settings/myinfo/timezone', body).then((r) => r.data),
    onSuccess: (data) => {
      message.success(t('msg.save.success'))
      useAuthStore.getState().updateUser({ offsetminutes: data.offsetminutes ?? null })
      qc.invalidateQueries({ queryKey: ['myinfo'] })
    },
    onError: (err) => message.error(err.response?.data?.detail || t('msg.save.error')),
  })
}

export function useMySubscriptions() {
  return useQuery({
    queryKey: ['myinfo-subscriptions'],
    queryFn: () => apiClient.get('/settings/myinfo/subscriptions').then((r) => r.data),
  })
}

export function useUpgradeProducts(servicecd, plancd = 'Pr') {
  return useQuery({
    queryKey: ['upgrade-products', servicecd, plancd],
    queryFn: () => apiClient.get('/settings/upgrade-products', { params: { servicecd, plancd } }).then((r) => r.data),
    enabled: !!servicecd,
  })
}

export function useUpgradePlan() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body) => apiClient.post('/settings/upgrade-plan', body).then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['myinfo-subscriptions'] })
    },
  })
}

// ─── Connectors ───────────────────────────────────────────────────────────────

export function useConnectors() {
  return useQuery({
    queryKey: ['settings-connectors'],
    queryFn: () => apiClient.get('/connectors').then((r) => r.data),
  })
}

export function useSaveConnector() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body) => apiClient.post('/connectors', body).then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['settings-connectors'] })
    },
  })
}

export function useDeleteConnector() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (connuid) => apiClient.delete(`/connectors/${connuid}`).then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['settings-connectors'] })
    },
  })
}

export function useTestConnectorHealth() {
  return useMutation({
    mutationFn: (connuid) => apiClient.post(`/connectors/${connuid}/test-health`).then((r) => r.data),
  })
}

export function useTestConnectorAuth() {
  return useMutation({
    mutationFn: (connuid) => apiClient.post(`/connectors/${connuid}/test-auth`).then((r) => r.data),
  })
}

export function useTestConnectorHealthInline() {
  return useMutation({
    mutationFn: (payload) => apiClient.post('/connectors/test-health-inline', payload).then((r) => r.data),
  })
}

export function useTestConnectorAuthInline() {
  return useMutation({
    mutationFn: (payload) => apiClient.post('/connectors/test-auth-inline', payload).then((r) => r.data),
  })
}
