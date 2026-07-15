import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { message } from 'antd'
import apiClient from '@/api/client'
import { t } from '@/stores/langStore'

export function useWhitelists() {
  return useQuery({
    queryKey: ['whitelists'],
    queryFn: () => apiClient.get('/whitelists').then((r) => r.data.whitelists),
  })
}

export function useSaveWhitelist() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (payload) => apiClient.post('/whitelists', payload).then((r) => r.data),
    onSuccess: () => {
      message.success(t('msg.save.success'))
      qc.invalidateQueries({ queryKey: ['whitelists'] })
    },
    onError: (err) => {
      const detail = err.response?.data?.detail
      message.error(detail ? t(detail) : t('msg.save.error'))
    },
  })
}

export function useDeleteWhitelist() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (whitelistuid) => apiClient.delete(`/whitelists/${whitelistuid}`).then((r) => r.data),
    onSuccess: () => {
      message.success(t('msg.delete.success'))
      qc.invalidateQueries({ queryKey: ['whitelists'] })
    },
    onError: (err) => {
      const detail = err.response?.data?.detail
      message.error(detail ? t(detail) : t('msg.delete.error'))
    },
  })
}
