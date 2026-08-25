import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { App } from 'antd'
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
    queryFn: () => apiClient.get('/settings/myinfo-v2').then((r) => r.data),
  })
}

export function useUpdateUsername() {
  const qc = useQueryClient()
  const { message } = App.useApp()
  return useMutation({
    mutationFn: (body) => apiClient.post('/settings/myinfo/username', body).then((r) => r.data),
    onSuccess: () => {
      message.success(t('msg.save.success'))
      qc.invalidateQueries({ queryKey: ['myinfo'] })
    },
    onError: (err) => { message.error(err.response?.data?.detail || t('msg.save.error')) },
  })
}

export function useUpdateTimezone() {
  const qc = useQueryClient()
  const { message } = App.useApp()
  return useMutation({
    mutationFn: (body) => apiClient.post('/settings/myinfo/timezone', body).then((r) => r.data),
    onSuccess: (data) => {
      message.success(t('msg.save.success'))
      useAuthStore.getState().updateUser({ offsetminutes: data.offsetminutes ?? null })
      qc.invalidateQueries({ queryKey: ['myinfo'] })
    },
    onError: (err) => { message.error(err.response?.data?.detail || t('msg.save.error')) },
  })
}

export function useUpdateMarketing() {
  const qc = useQueryClient()
  const { message } = App.useApp()
  return useMutation({
    mutationFn: (body) => apiClient.post('/settings/myinfo/marketing', body).then((r) => r.data),
    onSuccess: () => {
      message.success(t('msg.save.success'))
      qc.invalidateQueries({ queryKey: ['myinfo'] })
    },
    onError: (err) => { message.error(err.response?.data?.detail || t('msg.save.error')) },
  })
}

export function useMySubscriptions() {
  return useQuery({
    queryKey: ['myinfo-subscriptions'],
    queryFn: () => apiClient.get('/settings/myinfo/subscriptions').then((r) => r.data),
  })
}

export function useMyUsage(startDate, endDate, servicecd = 'Do') {
  return useQuery({
    queryKey: ['myinfo-usage', startDate, endDate, servicecd],
    queryFn: () => apiClient.get('/settings/myinfo/usage-v2', {
      params: { start_date: startDate, end_date: endDate, servicecd },
    }).then((r) => r.data),
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

export function useProCancel() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body) => apiClient.post('/settings/myinfo/pro-cancel', body).then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['myinfo-subscriptions'] })
    },
  })
}

export function useProCancelUndo() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body) => apiClient.post('/settings/myinfo/pro-cancel-undo', body).then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['myinfo-subscriptions'] })
    },
  })
}

// ─── Tenant Subscription (신규 테넌트 셀프 생성) ────────────────────────────────

export function useTenantSubscriptionInit() {
  return useQuery({
    queryKey: ['tenant-subscription-init'],
    queryFn: () => apiClient.get('/settings/tenant-subscription/init').then((r) => r.data),
  })
}

export function useCreateTenantSubscription() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body) => apiClient.post('/settings/tenant-subscription', body).then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['myinfo'] })
    },
  })
}

// ─── Tenant Manage (구독 관리) ──────────────────────────────────────────────────

export function useTenantManageSubscriptions() {
  return useQuery({
    queryKey: ['tenant-manage-subscriptions'],
    queryFn: () => apiClient.get('/settings/tenant-manage/subscriptions').then((r) => r.data),
  })
}

export function useTenantManageTeamProducts(servicecd) {
  return useQuery({
    queryKey: ['tenant-manage-team-products', servicecd],
    queryFn: () => apiClient.get('/settings/tenant-manage/team-products', { params: { servicecd } }).then((r) => r.data),
    enabled: !!servicecd,
  })
}

export function useChangeTenantSubscription() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body) => apiClient.post('/settings/tenant-manage/subscription-change', body).then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['tenant-manage-subscriptions'] })
    },
  })
}

export function useTenantManageTenantInfo() {
  return useQuery({
    queryKey: ['tenant-manage-tenant-info'],
    queryFn: () => apiClient.get('/settings/tenant-manage/tenant-info').then((r) => r.data),
  })
}

export function useTenantManageBasicInfo() {
  return useQuery({
    queryKey: ['tenant-manage-basic-info'],
    queryFn: () => apiClient.get('/settings/tenant-manage/basic-info').then((r) => r.data),
  })
}

export function useSaveTenantManageBasicInfo() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (formData) => apiClient.post('/settings/tenant-manage/basic-info', formData).then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['tenant-manage-basic-info'] })
      qc.invalidateQueries({ queryKey: ['tenant-manage-tenant-info'] })
    },
  })
}

export function useTenantManageOtherSubscriptions(options = {}) {
  return useQuery({
    queryKey: ['tenant-manage-other-subscriptions'],
    queryFn: () => apiClient.get('/settings/tenant-manage/other-subscriptions').then((r) => r.data),
    ...options,
  })
}

export function usePurchaseTenantManageOtherSubscription() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body) => apiClient.post('/settings/tenant-manage/other-subscription-purchase', body).then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['tenant-manage-other-subscriptions'] })
    },
  })
}

export function useCancelTenantManageOtherSubscription() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body) => apiClient.post('/settings/tenant-manage/other-subscription-cancel', body).then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['tenant-manage-other-subscriptions'] })
    },
  })
}

export function useCancelUndoTenantManageOtherSubscription() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body) => apiClient.post('/settings/tenant-manage/other-subscription-cancel-undo', body).then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['tenant-manage-other-subscriptions'] })
    },
  })
}

export function useTenantManageCreditSubscriptions() {
  return useQuery({
    queryKey: ['tenant-manage-credit-subscriptions'],
    queryFn: () => apiClient.get('/settings/tenant-manage/credit-subscriptions').then((r) => r.data),
  })
}

export function usePurchaseTenantManageCreditSubscription() {
  const qc = useQueryClient()
  const { message } = App.useApp()
  return useMutation({
    mutationFn: (body) => apiClient.post('/settings/tenant-manage/credit-subscription-purchase', body).then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['tenant-manage-credit-subscriptions'] })
    },
    onError: (err) => {
      const detail = err.response?.data?.detail
      message.error(detail ? t(detail) : t('msg.save.error'))
    },
  })
}

export function useMyInfoCreditPurchase(enabled = true) {
  return useQuery({
    queryKey: ['myinfo-credit-purchase'],
    queryFn: () => apiClient.get('/settings/myinfo/credit-purchase').then((r) => r.data),
    enabled,
  })
}

export function usePurchaseMyInfoCredit() {
  const qc = useQueryClient()
  const { message } = App.useApp()
  return useMutation({
    mutationFn: (body) => apiClient.post('/settings/myinfo/credit-purchase', body).then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['myinfo-credit-purchase'] })
    },
    onError: (err) => {
      const detail = err.response?.data?.detail
      message.error(detail ? t(detail) : t('msg.save.error'))
    },
  })
}

export function useTenantManageOverview() {
  return useQuery({
    queryKey: ['tenant-manage-overview'],
    queryFn: () => apiClient.get('/settings/tenant-manage/overview').then((r) => r.data),
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
