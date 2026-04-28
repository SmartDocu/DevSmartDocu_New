import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { App } from 'antd'
import apiClient from '@/api/client'
import { t } from '@/stores/langStore'

export function useDocDatasets(docid) {
  return useQuery({
    queryKey: ['doc-datasets', docid],
    queryFn: () => apiClient.get(`/docs/${docid}/doc-params`).then((r) => r.data),
    enabled: !!docid,
  })
}

export function useSaveDocDatasets(docid) {
  const qc = useQueryClient()
  const { message } = App.useApp()
  return useMutation({
    mutationFn: (body) => apiClient.post(`/docs/${docid}/doc-params`, body).then((r) => r.data),
    onSuccess: () => {
      message.success(t('msg.save.success'))
      qc.invalidateQueries({ queryKey: ['doc-datasets', String(docid)] })
    },
    onError: (err) => {
      const detail = err.response?.data?.detail
      message.error(detail ? t(detail) : t('msg.save.error'))
    },
  })
}
