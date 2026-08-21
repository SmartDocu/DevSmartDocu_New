import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { App } from 'antd'
import apiClient from '@/api/client'
import { t } from '@/stores/langStore'
import { useOpenInTab } from '@/hooks/useOpenInTab'

export function usePaymentConfig() {
  return useQuery({
    queryKey: ['payment-config'],
    queryFn: () => apiClient.get('/payments/config').then((r) => r.data),
    staleTime: Infinity,
  })
}

export function usePaymentMethods() {
  return useQuery({
    queryKey: ['payment-methods'],
    queryFn: () => apiClient.get('/payments/methods').then((r) => r.data),
  })
}

export function useSaveBillingKey() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body) => apiClient.post('/payments/methods/billing-key', body).then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['payment-methods'] })
    },
  })
}

export function useDeletePaymentMethod() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (paymentMethoduid) => apiClient.delete(`/payments/methods/${paymentMethoduid}`).then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['payment-methods'] })
    },
  })
}

export function useSetDefaultPaymentMethod() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (paymentMethoduid) => apiClient.post(`/payments/methods/${paymentMethoduid}/set-default`).then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['payment-methods'] })
    },
  })
}

export function useChargePaymentMethod() {
  return useMutation({
    mutationFn: ({ paymentMethoduid, amount, orderName }) =>
      apiClient.post(`/payments/methods/${paymentMethoduid}/charge`, { amount, order_name: orderName }).then((r) => r.data),
  })
}

export const PAYMENT_METHOD_REQUIRED = 'msg.payment.method.required'

/**
 * 실제 상품 구매(플랜 변경/인원·기능 추가/크레딧 구매 등) 화면 공용 결제수단 체크.
 * 등록된 결제수단이 없으면 구매 전에 등록 화면으로 안내한다.
 * paymentManagePath: 기업 화면은 'org/payment-manage', 개인 화면은 'payment-manage'.
 */
export function usePaymentGate(paymentManagePath) {
  const { modal } = App.useApp()
  const openInTab = useOpenInTab()
  const { data: methodsData = {} } = usePaymentMethods()
  const hasPaymentMethod = (methodsData.methods || []).some(
    (m) => m.is_default && m.payment_method_status === 'Active',
  )

  const promptCardRegistration = () => {
    modal.confirm({
      title: t('ttl.tenant.manage.payment'),
      content: t(PAYMENT_METHOD_REQUIRED),
      okText: t('btn.payment.register'),
      cancelText: t('btn.cancel'),
      onOk: () => openInTab(paymentManagePath, '', t('ttl.tenant.manage.payment')),
    })
  }

  return { hasPaymentMethod, promptCardRegistration }
}
