import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { message } from 'antd'
import { t } from '@/stores/langStore'
import apiClient from '@/api/client'

export function useObjects(chapteruid) {
  return useQuery({
    queryKey: ['objects', chapteruid],
    queryFn: () => apiClient.get('/objects', { params: { chapteruid } }).then((r) => r.data.objects),
    enabled: !!chapteruid,
  })
}

export function useSaveObject() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body) => apiClient.post('/objects', body).then((r) => r.data),
    onSuccess: (_data, body) => {
      message.success(t('msg.save.success'))
      qc.invalidateQueries({ queryKey: ['objects', body.chapteruid] })
    },
    onError: (err) => {
      message.error(err.response?.data?.detail || t('msg.save.error'))
    },
  })
}

export function useDeleteObject() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ objectuid, chapteruid }) =>
      apiClient.delete(`/objects/${objectuid}`).then((r) => r.data),
    onSuccess: (_data, { chapteruid }) => {
      message.success(t('msg.delete.success'))
      qc.invalidateQueries({ queryKey: ['objects', chapteruid] })
    },
    onError: (err) => {
      message.error(err.response?.data?.detail || t('msg.delete.error'))
    },
  })
}
