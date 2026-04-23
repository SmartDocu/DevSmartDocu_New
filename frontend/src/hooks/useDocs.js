import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { message } from 'antd'
import apiClient from '@/api/client'
import { t } from '@/stores/langStore'

export function useDocs() {
  return useQuery({
    queryKey: ['docs'],
    queryFn: () => apiClient.get('/docs').then((r) => r.data.docs),
  })
}

export function useProjects() {
  return useQuery({
    queryKey: ['docs-projects'],
    queryFn: () => apiClient.get('/docs/projects').then((r) => r.data.projects),
  })
}

export function useSaveDoc() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (formData) => apiClient.post('/docs', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }).then((r) => r.data),
    onSuccess: () => {
      message.success(t('msg.saved'))
      qc.invalidateQueries({ queryKey: ['docs'] })
    },
    onError: (err) => {
      const detail = err.response?.data?.detail
      message.error(detail ? t(detail) : t('msg.save.error'))
    },
  })
}

export function useDeleteDoc() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (docid) => apiClient.delete(`/docs/${docid}`).then((r) => r.data),
    onSuccess: () => {
      message.success(t('msg.deleted'))
      qc.invalidateQueries({ queryKey: ['docs'] })
    },
    onError: (err) => {
      const detail = err.response?.data?.detail
      message.error(detail ? t(detail) : t('msg.delete.error'))
    },
  })
}
