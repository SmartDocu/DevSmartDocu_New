import { useMutation, useQuery } from '@tanstack/react-query'
import apiClient from '@/api/client'

// 회원 탈퇴 페이지(/withdraw) 전용 훅 — 서버 응답 구조는 backend/app/routers/withdraw.py 참고

export function useWithdrawOverview() {
  return useQuery({
    queryKey: ['withdraw-overview'],
    queryFn: () => apiClient.get('/withdraw/overview').then((r) => r.data),
    staleTime: 0,
    gcTime: 0,
  })
}

export function useTransferAdmin() {
  return useMutation({
    mutationFn: (body) => apiClient.post('/withdraw/transfer-admin', body).then((r) => r.data),
  })
}

export function useEndOrgSubscription() {
  return useMutation({
    mutationFn: (body) => apiClient.post('/withdraw/end-org-subscription', body).then((r) => r.data),
  })
}

export function useSubmitWithdraw() {
  return useMutation({
    mutationFn: (body) => apiClient.post('/withdraw/submit', body).then((r) => r.data),
  })
}
