import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { message } from 'antd'
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
      message.success('저장되었습니다.')
      qc.invalidateQueries({ queryKey: ['settings-servers'] })
      qc.invalidateQueries({ queryKey: ['datas-dbconnectors'] })
    },
    onError: (err) => message.error(err.response?.data?.detail || '저장에 실패했습니다.'),
  })
}

export function useDeleteServer() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (connectid) => apiClient.delete(`/settings/servers/${connectid}`).then((r) => r.data),
    onSuccess: () => {
      message.success('삭제되었습니다.')
      qc.invalidateQueries({ queryKey: ['settings-servers'] })
      qc.invalidateQueries({ queryKey: ['datas-dbconnectors'] })
    },
    onError: (err) => message.error(err.response?.data?.detail || '삭제에 실패했습니다.'),
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
      message.success('저장되었습니다.')
      qc.invalidateQueries({ queryKey: ['settings-projects'] })
    },
    onError: (err) => message.error(err.response?.data?.detail || '저장에 실패했습니다.'),
  })
}

export function useDeleteProject() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (projectid) => apiClient.delete(`/settings/projects/${projectid}`).then((r) => r.data),
    onSuccess: () => {
      message.success('삭제되었습니다.')
      qc.invalidateQueries({ queryKey: ['settings-projects'] })
    },
    onError: (err) => message.error(err.response?.data?.detail || '삭제에 실패했습니다.'),
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
      message.success('저장되었습니다.')
      qc.invalidateQueries({ queryKey: ['settings-tenants'] })
    },
    onError: (err) => message.error(err.response?.data?.detail || '저장에 실패했습니다.'),
  })
}

export function useDeleteTenant() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (tenantid) => apiClient.delete(`/settings/tenants/${tenantid}`).then((r) => r.data),
    onSuccess: () => {
      message.success('삭제되었습니다.')
      qc.invalidateQueries({ queryKey: ['settings-tenants'] })
    },
    onError: (err) => message.error(err.response?.data?.detail || '삭제에 실패했습니다.'),
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
      message.success('사용자명이 저장되었습니다.')
      qc.invalidateQueries({ queryKey: ['myinfo'] })
    },
    onError: (err) => message.error(err.response?.data?.detail || '저장에 실패했습니다.'),
  })
}
