import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { message } from 'antd'
import apiClient from '@/api/client'

export function useObjectTypes() {
  return useQuery({
    queryKey: ['objecttypes'],
    queryFn: () => apiClient.get('/objects/types').then((r) => r.data.objecttypes),
  })
}

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
      message.success('저장되었습니다.')
      qc.invalidateQueries({ queryKey: ['objects', body.chapteruid] })
    },
    onError: (err) => {
      message.error(err.response?.data?.detail || '저장에 실패했습니다.')
    },
  })
}

export function useDeleteObject() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ objectuid, chapteruid }) =>
      apiClient.delete(`/objects/${objectuid}`).then((r) => r.data),
    onSuccess: (_data, { chapteruid }) => {
      message.success('삭제되었습니다.')
      qc.invalidateQueries({ queryKey: ['objects', chapteruid] })
    },
    onError: (err) => {
      message.error(err.response?.data?.detail || '삭제에 실패했습니다.')
    },
  })
}
