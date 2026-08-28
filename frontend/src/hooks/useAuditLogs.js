import { useQuery } from '@tanstack/react-query'
import apiClient from '@/api/client'

// ─── Audit Logs (admin, roleid=7 전용) ─────────────────────────────────────────

export function usePrivacyConsentLogs(params) {
  return useQuery({
    queryKey: ['audit-privacy-consent', params],
    queryFn: () => apiClient.get('/auditlogs/privacy-consent', { params }).then((r) => r.data),
    placeholderData: (prev) => prev,
  })
}

export function useAdminActionLogs(params) {
  return useQuery({
    queryKey: ['audit-admin-actions', params],
    queryFn: () => apiClient.get('/auditlogs/admin-actions', { params }).then((r) => r.data),
    placeholderData: (prev) => prev,
  })
}

export function useWorkLogs(params) {
  return useQuery({
    queryKey: ['audit-work', params],
    queryFn: () => apiClient.get('/auditlogs/work', { params }).then((r) => r.data),
    placeholderData: (prev) => prev,
  })
}

export function useLoginLogs(params) {
  return useQuery({
    queryKey: ['audit-login', params],
    queryFn: () => apiClient.get('/auditlogs/login', { params }).then((r) => r.data),
    placeholderData: (prev) => prev,
  })
}
